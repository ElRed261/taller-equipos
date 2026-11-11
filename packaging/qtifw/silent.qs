// Instalación no interactiva (control script de prueba).
//
// Reproduce el flujo completo sin pantalla: marca las páginas del wizard
// invisibles y ejecuta la instalación, como lo haría un usuario con clics.
// Es la forma reproducible de probar que el componente y su script cargan.
//
//   dist/taller-equipos-instalador --script packaging/qtifw/silent.qs

function Controller()
{
    installer.autoAcceptLicenses = true;

    // cada página con UI, oculta: el run va directo
    installer.setDefaultPageVisible(QInstaller.Introduction, false);
    installer.setDefaultPageVisible(QInstaller.TargetDirectory, false);
    installer.setDefaultPageVisible(QInstaller.ComponentSelection, false);
    installer.setDefaultPageVisible(QInstaller.LicenseCheck, false);
    installer.setDefaultPageVisible(QInstaller.StartMenuSelection, false);
    installer.setDefaultPageVisible(QInstaller.ReadyForInstallation, false);
    installer.setDefaultPageVisible(QInstaller.PerformInstallation, false);
    installer.setDefaultPageVisible(QInstaller.InstallationFinished, false);

    // la instalación misma: sin esto el wizard se queda esperando clics
    installer.performInstall();
}

Controller.prototype.FinishedPageCallback = function ()
{
    gui.clickButton(buttons.FinishButton);
};
