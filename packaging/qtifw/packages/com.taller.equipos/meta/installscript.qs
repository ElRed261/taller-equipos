// Instalación del taller de equipos con Qt Installer Framework.
//
// Copia el árbol compilado (data → @TargetDir@), crea los accesos que la
// sesión espera (entrada XDG en el menú, lanzador en ~/.local/bin), y abre el
// programa al terminar sin bloquearse.
//
// Lecciones ya pagadas, en el orden en que mordieron:
//   - QtIFW 4.7 no tiene "ExecuteDetached" (el error "Operation does not
//     exist" lo confirmó) y "Execute" espera al hijo: un instalador headless
//     quedaba colgado una hora con la app en primer plano.
//   - "@StartMenuDir@" y "@DesktopDir@" quedan vacíos en el modo no
//     interactivo; los atajos morían en rutas relativas. "@HomeDir@" sí
//     resuelve (es lo que usa TargetDir).
//
// Por eso, en Linux, los accesos y el lanzamiento van por /bin/sh, que es el
// único camino cuyo comportamiento controlamos en las dos modalidades.

function Component()
{
    // constructor por defecto
}

Component.prototype.createOperations = function ()
{
    // primero el comportamiento estándar: extraer `data` a @TargetDir@
    component.createOperations();

    if (systemInfo.productType === "windows") {
        component.addOperation(
            "CreateShortcut",
            "@TargetDir@\\taller-equipos.exe",
            "@HomeDir@\\.local\\share\\applications\\taller-equipos.lnk"
        );
        component.addOperation(
            "Execute", "cmd", "/c", "start", "",
            "@TargetDir@\\taller-equipos.exe"
        );
    } else {
        // Entrada del menú de aplicaciones (XDG, independiente del idioma) y
        // lanzador en ~/.local/bin, con el logo que viaja con el binario.
        component.addOperation(
            "Execute", "/bin/sh", "-c",
            "mkdir -p '@HomeDir@/.local/bin' '@HomeDir@/.local/share/applications' && " +
            "ln -sf '@TargetDir@/taller-equipos.bin' '@HomeDir@/.local/bin/taller-equipos' && " +
            "printf '[Desktop Entry]\\nType=Application\\nName=Taller de equipos\\n" +
            "Comment=Registro de entrada y salida de equipos\\n" +
            "Exec=\"@TargetDir@/taller-equipos.bin\"\\n" +
            "Icon=@TargetDir@/taller/ui/assets/logo.png\\n" +
            "Terminal=false\\nCategories=Office;Database;\\n' " +
            "> '@HomeDir@/.local/share/applications/taller-equipos.desktop'"
        );

        // Abrir al terminar: el lanzador despega y sale al instante, así el
        // instalador termina limpio en CLI y con GUI.
        component.addOperation(
            "Execute", "/bin/sh", "-c",
            "setsid '@TargetDir@/taller-equipos.bin' >/dev/null 2>&1 &"
        );
    }
};
