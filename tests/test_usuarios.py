"""Cuentas de la aplicación: contraseñas, ingreso y administración.

Lo que se fija acá es lo que hace que la auditoría signifique algo: para editar hay
que entrar con una contraseña, el nombre que queda anotado es el de esa cuenta, y un
mensaje de error no cuenta si el usuario existe.
"""

from __future__ import annotations

import datetime as dt

import pytest

from taller.database.repositories import (
    UsuarioDuplicado,
    UsuarioRepository,
)
from taller.schemas.usuario import UsuarioLeido
from taller.seguridad import LARGO_MINIMO, clave_aceptable, hashear, necesita_rehash, verificar
from taller.servicios import ServicioTaller

CLAVE = "una-clave-larga-y-buena"


class TestHash:
    def test_la_clave_correcta_verifica(self) -> None:
        assert verificar(hashear(CLAVE), CLAVE) is True

    def test_la_clave_incorrecta_no_verifica(self) -> None:
        assert verificar(hashear(CLAVE), "otra-clave-larga-y-mala") is False

    def test_un_hash_corrupto_no_revienta(self) -> None:
        # Una fila a medio migrar no puede tumbar el arranque del programa.
        assert verificar("esto no es un hash", CLAVE) is False
        assert verificar(None, CLAVE) is False
        assert verificar("", CLAVE) is False

    def test_una_clave_vacia_no_entra(self) -> None:
        assert verificar(hashear(CLAVE), "") is False

    def test_el_hash_no_contiene_la_clave(self) -> None:
        assert CLAVE not in hashear(CLAVE)

    def test_un_hash_nuevo_no_necesita_rehash(self) -> None:
        assert necesita_rehash(hashear(CLAVE)) is False

    def test_un_hash_corrupto_no_necesita_rehash_ni_revienta(self) -> None:
        assert necesita_rehash("basura") is False


class TestClaveAceptable:
    def test_corta_se_rechaza_con_el_motivo(self) -> None:
        motivo = clave_aceptable("corta")
        assert motivo is not None
        assert str(LARGO_MINIMO) in motivo

    def test_larga_se_acepta(self) -> None:
        assert clave_aceptable(CLAVE) is None

    def test_repetitiva_se_rechaza(self) -> None:
        assert clave_aceptable("aaaaaaaaaaaaaaaa") is not None

    def test_con_espacios_en_los_bordes_se_rechaza(self) -> None:
        assert clave_aceptable(" clave-larga-y-buena ") is not None


@pytest.fixture
def repositorio(session) -> UsuarioRepository:  # noqa: ANN001 - fixture del proyecto
    return UsuarioRepository(session)


@pytest.fixture
def cuenta_limpia(session) -> UsuarioLeido:  # noqa: ANN001
    """Una cuenta de prueba que se borra al terminar, pase lo que pase."""
    from sqlalchemy import delete

    from taller.database.models import Usuario

    repositorio = UsuarioRepository(session)
    creada = repositorio.crear("prueba-operador", CLAVE)
    try:
        yield creada
    finally:
        session.execute(delete(Usuario).where(Usuario.nombre.like("prueba-%")))


class TestRepositorio:
    def test_crear_y_autenticar(self, repositorio: UsuarioRepository) -> None:
        creada = repositorio.crear("prueba-ana", CLAVE)
        assert creada.nombre == "prueba-ana"
        assert creada.es_admin is False

        autenticada = repositorio.autenticar("prueba-ana", CLAVE)
        assert autenticada is not None
        assert autenticada.id == creada.id

    def test_el_nombre_no_distingue_mayusculas(
        self, repositorio: UsuarioRepository
    ) -> None:
        repositorio.crear("prueba-ana", CLAVE)
        assert repositorio.autenticar("PRUEBA-ANA", CLAVE) is not None

    def test_la_clave_incorrecta_no_entra(self, repositorio: UsuarioRepository) -> None:
        repositorio.crear("prueba-ana", CLAVE)
        assert repositorio.autenticar("prueba-ana", "otra-clave-larga-mala") is None

    def test_un_usuario_inexistente_no_entra(
        self, repositorio: UsuarioRepository
    ) -> None:
        assert repositorio.autenticar("prueba-nadie", CLAVE) is None

    def test_un_usuario_inactivo_no_entra(self, repositorio: UsuarioRepository) -> None:
        creada = repositorio.crear("prueba-ana", CLAVE)
        repositorio.alternar_activo(creada.id)
        assert repositorio.autenticar("prueba-ana", CLAVE) is None

    def test_el_nombre_repetido_se_rechaza(
        self, repositorio: UsuarioRepository
    ) -> None:
        repositorio.crear("prueba-ana", CLAVE)
        with pytest.raises(UsuarioDuplicado):
            repositorio.crear("PRUEBA-ANA", CLAVE)

    def test_una_clave_corta_no_se_guarda(
        self, repositorio: UsuarioRepository
    ) -> None:
        with pytest.raises(ValueError, match="caracteres"):
            repositorio.crear("prueba-corta", "corta")

    def test_el_dto_no_lleva_el_hash(self, repositorio: UsuarioRepository) -> None:
        creada = repositorio.crear("prueba-ana", CLAVE)
        # El DTO es lo único que sale del repositorio: si no tiene el campo, el
        # hash no puede llegar a una pantalla ni a un log por descuido.
        assert not hasattr(creada, "password_hash")
        assert CLAVE not in repr(creada)

    def test_autenticar_registra_el_ultimo_acceso(
        self, repositorio: UsuarioRepository
    ) -> None:
        repositorio.crear("prueba-ana", CLAVE)
        antes = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=5)
        autenticada = repositorio.autenticar("prueba-ana", CLAVE)
        assert autenticada is not None
        assert autenticada.ultimo_acceso is not None
        assert autenticada.ultimo_acceso > antes

    def test_no_se_desactiva_al_ultimo_administrador(
        self, repositorio: UsuarioRepository
    ) -> None:
        administradores = [u for u in repositorio.listar() if u.es_admin and u.activo]
        if len(administradores) != 1:
            pytest.skip("la base no tiene exactamente un administrador activo")
        with pytest.raises(ValueError, match="administrador"):
            repositorio.alternar_activo(administradores[0].id)

    def test_asignar_administrador_a_una_cuenta_nueva(
        self, repositorio: UsuarioRepository
    ) -> None:
        creada = repositorio.crear("prueba-jefe", CLAVE, es_admin=True)
        assert repositorio.obtener(creada.id).es_admin is True
        # Y vuelve a operador sin problema, porque queda otro administrador.
        assert repositorio.hacer_administrador(creada.id, es_admin=False).es_admin is False

    def test_fijar_clave_a_una_cuenta_que_ya_existia(
        self, repositorio: UsuarioRepository
    ) -> None:
        from sqlalchemy import delete

        from taller.database.models import Usuario

        session = repositorio._s  # noqa: SLF001 - la fixture ya es de bajo nivel
        session.add(Usuario(nombre="prueba-heredada"))
        session.flush()
        assert repositorio.autenticar("prueba-heredada", CLAVE) is None

        repositorio.fijar_clave_de_existente("prueba-heredada", CLAVE, es_admin=False)
        assert repositorio.autenticar("prueba-heredada", CLAVE) is not None
        session.execute(delete(Usuario).where(Usuario.nombre.like("prueba-%")))


class TestDialogoIngreso:
    def _dialogo(self, qtbot, autenticador):  # noqa: ANN001, ANN202
        from taller.ui.views.ingreso_view import DialogoIngreso

        dialogo = DialogoIngreso(autenticador=autenticador)
        qtbot.addWidget(dialogo)
        return dialogo

    def test_un_solo_mensaje_para_usuario_inexistente_y_clave_mala(
        self, qtbot: object
    ) -> None:
        dialogo = self._dialogo(qtbot, lambda *_: None)

        dialogo.usuario_entrada.setText("prueba-nadie")
        dialogo.clave.setText("lo-que-sea-largo")
        assert dialogo.intentar() is False
        primero = dialogo.error.text()

        dialogo.usuario_entrada.setText("prueba-ana")
        dialogo.clave.setText("otra-cosa-larga")
        assert dialogo.intentar() is False
        segundo = dialogo.error.text()

        # Si los mensajes difieren, el formulario sirve para averiguar quién existe.
        assert primero == segundo
        assert dialogo.usuario is None

    def test_con_credenciales_buenas_entra_y_guarda_el_nombre(
        self, qtbot: object
    ) -> None:
        cuenta = UsuarioLeido(id=7, nombre="ana", es_admin=True)
        dialogo = self._dialogo(qtbot, lambda nombre, clave: cuenta)

        dialogo.usuario_entrada.setText("ana")
        dialogo.clave.setText(CLAVE)
        assert dialogo.intentar() is True
        assert dialogo.usuario == "ana"
        assert dialogo.es_admin is True

    def test_al_fallar_limpia_la_contrasena(self, qtbot: object) -> None:
        dialogo = self._dialogo(qtbot, lambda *_: None)
        dialogo.usuario_entrada.setText("ana")
        dialogo.clave.setText(CLAVE)
        dialogo.intentar()
        assert dialogo.clave.text() == ""

    def test_sin_datos_no_consulta_al_servidor(self, qtbot: object) -> None:
        llamadas: list[tuple[str, str]] = []
        dialogo = self._dialogo(qtbot, lambda n, c: llamadas.append((n, c)) or None)
        assert dialogo.intentar() is False
        assert llamadas == []


class TestPrimerAdministrador:
    def _dialogo(self, qtbot):  # noqa: ANN001, ANN202
        from taller.ui.views.ingreso_view import DialogoPrimerAdministrador

        dialogo = DialogoPrimerAdministrador(creador=ServicioTaller.crear_administrador)
        qtbot.addWidget(dialogo)
        return dialogo

    def test_las_contrasenas_distintas_se_rechazan(self, qtbot: object) -> None:
        dialogo = self._dialogo(qtbot)
        dialogo.nombre.setText("prueba-admin")
        dialogo.clave.setText(CLAVE)
        dialogo.repetida.setText(CLAVE + "x")
        assert dialogo.crear() is False
        assert "no coinciden" in dialogo.error.text()

    def test_una_clave_corta_se_rechaza_por_el_motivo(self, qtbot: object) -> None:
        dialogo = self._dialogo(qtbot)
        dialogo.nombre.setText("prueba-admin")
        dialogo.clave.setText("corta")
        dialogo.repetida.setText("corta")
        assert dialogo.crear() is False
        assert str(LARGO_MINIMO) in dialogo.error.text()

    def test_sin_nombre_se_rechaza(self, qtbot: object) -> None:
        dialogo = self._dialogo(qtbot)
        dialogo.clave.setText(CLAVE)
        dialogo.repetida.setText(CLAVE)
        assert dialogo.crear() is False


class TestDialogoClave:
    def _dialogo(self, qtbot, nombre: str = ""):  # noqa: ANN001, ANN202
        from taller.ui.views.ingreso_view import DialogoClave

        dialogo = DialogoClave(nombre=nombre)
        qtbot.addWidget(dialogo)
        return dialogo

    def test_acepta_una_clave_valida(self, qtbot: object) -> None:
        dialogo = self._dialogo(qtbot, nombre="ana")
        dialogo.entrada.setText(CLAVE)
        dialogo.repetida.setText(CLAVE)
        assert dialogo.aceptar() is True
        assert dialogo.clave == CLAVE

    def test_rechaza_si_no_coinciden(self, qtbot: object) -> None:
        dialogo = self._dialogo(qtbot, nombre="ana")
        dialogo.entrada.setText(CLAVE)
        dialogo.repetida.setText(CLAVE + "x")
        assert dialogo.aceptar() is False

    def test_sin_nombre_no_acepta(self, qtbot: object) -> None:
        dialogo = self._dialogo(qtbot)
        dialogo.entrada.setText(CLAVE)
        dialogo.repetida.setText(CLAVE)
        assert dialogo.aceptar() is False


class TestModeloDeUsuarios:
    def test_muestra_las_cuatro_columnas(self, qtbot: object) -> None:
        from PySide6.QtCore import Qt

        from taller.ui.models.usuarios_table_model import COLUMNAS, UsuariosTableModel

        modelo = UsuariosTableModel(
            [
                UsuarioLeido(id=1, nombre="ana", es_admin=True),
                UsuarioLeido(id=2, nombre="beto", activo=False),
            ]
        )
        assert modelo.rowCount() == 2
        assert modelo.columnCount() == len(COLUMNAS) == 4
        assert modelo.data(modelo.index(0, 1), Qt.ItemDataRole.DisplayRole) == "Activo"
        assert modelo.data(modelo.index(0, 2), Qt.ItemDataRole.DisplayRole) == "Administrador"
        assert modelo.data(modelo.index(1, 1), Qt.ItemDataRole.DisplayRole) == "Inactivo"
        assert modelo.data(modelo.index(1, 3), Qt.ItemDataRole.DisplayRole) == "nunca"


class TestPestanaDeUsuarios:
    def test_no_existe_para_quien_no_administra(self, qtbot: object) -> None:
        from tests.test_views import ServicioFalso

        from taller.ui.views.configuracion_view import ConfiguracionView

        vista = ConfiguracionView(ServicioFalso(es_admin=False))
        qtbot.addWidget(vista)
        titulos = [vista.pestanas.tabText(i) for i in range(vista.pestanas.count())]
        assert "Usuarios" not in titulos
        assert vista.usuarios is None

    def test_existe_para_un_administrador(self, qtbot: object) -> None:
        from tests.test_views import ServicioFalso

        from taller.ui.views.configuracion_view import ConfiguracionView

        servicio = ServicioFalso(es_admin=True)
        servicio.listar_usuarios = lambda: [UsuarioLeido(id=1, nombre="ana", es_admin=True)]
        vista = ConfiguracionView(servicio)
        qtbot.addWidget(vista)
        titulos = [vista.pestanas.tabText(i) for i in range(vista.pestanas.count())]
        assert "Usuarios" in titulos
        assert vista.usuarios is not None

    def test_no_deja_desactivarse_a_si_mismo(self, qtbot: object) -> None:
        from PySide6.QtCore import QItemSelectionModel
        from tests.test_views import ServicioFalso

        from taller.ui.views.configuracion_view import ConfiguracionView

        servicio = ServicioFalso(usuario="ana", es_admin=True)
        servicio.listar_usuarios = lambda: [UsuarioLeido(id=1, nombre="ana", es_admin=True)]
        vista = ConfiguracionView(servicio)
        qtbot.addWidget(vista)
        assert vista.usuarios is not None
        vista.usuarios.tabla.selectionModel().select(
            vista.usuarios.tabla.model().index(0, 0),
            QItemSelectionModel.SelectionFlag.Select
            | QItemSelectionModel.SelectionFlag.Rows,
        )
        assert vista.usuarios.boton_estado.isEnabled() is False
