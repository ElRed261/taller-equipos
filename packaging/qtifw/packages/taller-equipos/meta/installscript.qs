// Instalación del taller de equipos con Qt Installer Framework.
//
// El wizard de QtIFW instalará el árbol compilado (taller-equipos.bin o .exe más
// sus dependencias, que viajan dentro de `data`) y crea los accesos directos del
// grupo en el menú. Después la PUESTA EN MARCHA (nuestra, dentro de la app) lleva
// la configuración de la base a la base de datos y de la marca — eso NO se debe
// duplicar en el instalador.
//
// Referencias: ifw-tools, installscript.qs del ejemplo de Online Installer.

Component.prototype.createOperations = function () {
    var operaciones = component.createOperations();

    // Copiar el árbol compilado, tal cual sale de pyside6-deploy.
    operaciones.push(component.addOperation("Extract", "@TargetDir@"));

    var ejecutable = systemInfo.productType === "windows" ? "taller-equipos.exe" : "taller-equipos.bin";
    var extensionShortcut = systemInfo.productType === "windows" ? ".lnk" : ".desktop";

    var grupo = "@ApplicationsDir@/taller-equipos";

    // Acceso directo del menú (Inicio en Windows, grupos en Linux y macOS).
    operaciones.push(component.addOperation(
        "CreateShortcut",
        "@TargetDir@/" + ejecutable,
        grupo + "/taller-equipos" + extensionShortcut,
        "icon,workspace,actions,comments,tags="
    ));

    // Acceso directo en el escritorio: la acción principal de todo el día.
    operaciones.push(component.addOperation(
        "CreateShortcut",
        "@TargetDir@/" + ejecutable,
        "@DesktopDir@/taller-equipos" + extensionShortcut,
        "icon,workspace,actions,comments,tags="
    ));

    // Ejecutar el programa al terminar: ahí aparece la Puesta en marcha propia.
    operaciones.push(component.addOperation(
        "Execute",
        "@TargetDir@/" + ejecutable,
        "", "", "", "LauncherWasStarted=true"
    ));

    return operaciones;
};
