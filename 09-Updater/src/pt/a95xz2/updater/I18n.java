package pt.a95xz2.updater;

import java.util.HashMap;
import java.util.Locale;

/**
 * Textos do updater em varios idiomas (tabela em codigo, carregada uma vez).
 * Segue sempre o idioma do sistema Android; sem traducao -> ingles.
 * Para acrescentar um idioma: juntar o codigo a CODES e uma coluna a cada linha de T.
 */
final class I18n {
    static final String[] CODES = {"pt", "en", "es", "fr", "de"};

    // chave, pt, en, es, fr, de
    private static final String[][] T = {
        {"title", "Atualização do sistema", "System update", "Actualización del sistema", "Mise à jour du système", "Systemaktualisierung"},
        {"installed", "Instalado", "Installed", "Instalado", "Installé", "Installiert"},
        {"firmware", "Firmware", "Firmware", "Firmware", "Firmware", "Firmware"},
        {"launcher", "Launcher", "Launcher", "Launcher", "Launcher", "Launcher"},
        {"updater", "Atualizador", "Updater", "Actualizador", "Programme de mise à jour", "Updater"},
        {"unknown", "desconhecida", "unknown", "desconocida", "inconnue", "unbekannt"},
        {"not_installed", "não instalado", "not installed", "no instalado", "non installé", "nicht installiert"},
        {"check", "Procurar atualizações", "Check for updates", "Buscar actualizaciones", "Rechercher des mises à jour", "Nach Updates suchen"},
        {"checking", "A procurar atualizações…", "Checking for updates…", "Buscando actualizaciones…", "Recherche de mises à jour…", "Suche nach Updates…"},
        {"hint", "Carregue em «Procurar atualizações» para ver se há novas versões.", "Press “Check for updates” to look for new versions.", "Pulse «Buscar actualizaciones» para ver si hay versiones nuevas.", "Appuyez sur « Rechercher des mises à jour » pour voir les nouvelles versions.", "„Nach Updates suchen“ drücken, um nach neuen Versionen zu suchen."},
        {"no_network", "Sem ligação à rede.", "No network connection.", "Sin conexión de red.", "Pas de connexion réseau.", "Keine Netzwerkverbindung."},
        {"no_info", "Não há informação de atualizações disponível.", "No update information available.", "No hay información de actualizaciones disponible.", "Aucune information de mise à jour disponible.", "Keine Update-Informationen verfügbar."},
        {"net_error", "Erro de rede: %s", "Network error: %s", "Error de red: %s", "Erreur réseau : %s", "Netzwerkfehler: %s"},
        {"sig_error", "Assinatura inválida: a informação de atualizações foi rejeitada.", "Invalid signature: the update information was rejected.", "Firma no válida: se ha rechazado la información de actualizaciones.", "Signature invalide : les informations de mise à jour ont été rejetées.", "Ungültige Signatur: Die Update-Informationen wurden abgelehnt."},
        {"bad_manifest", "Informação de atualizações inválida: %s", "Invalid update information: %s", "Información de actualizaciones no válida: %s", "Informations de mise à jour invalides : %s", "Ungültige Update-Informationen: %s"},
        {"up_to_date", "Está tudo atualizado.", "Everything is up to date.", "Todo está actualizado.", "Tout est à jour.", "Alles ist auf dem neuesten Stand."},
        {"found_n", "Atualizações disponíveis: %d", "Updates available: %d", "Actualizaciones disponibles: %d", "Mises à jour disponibles : %d", "Verfügbare Updates: %d"},
        {"fw_item", "Firmware %1$s (instalada: %2$s)", "Firmware %1$s (installed: %2$s)", "Firmware %1$s (instalada: %2$s)", "Firmware %1$s (installée : %2$s)", "Firmware %1$s (installiert: %2$s)"},
        {"delta", "Atualização incremental · %s", "Incremental update · %s", "Actualización incremental · %s", "Mise à jour incrémentielle · %s", "Inkrementelles Update · %s"},
        {"full_only", "Não há atualização automática a partir da versão instalada. Esta versão tem de ser gravada com um PC (imagem completa, %1$s). Instruções: %2$s", "There is no automatic update from the installed version. This version must be flashed with a PC (full image, %1$s). Instructions: %2$s", "No hay actualización automática desde la versión instalada. Esta versión debe grabarse con un PC (imagen completa, %1$s). Instrucciones: %2$s", "Aucune mise à jour automatique depuis la version installée. Cette version doit être flashée avec un PC (image complète, %1$s). Instructions : %2$s", "Kein automatisches Update von der installierten Version. Diese Version muss mit einem PC geflasht werden (vollständiges Image, %1$s). Anleitung: %2$s"},
        {"app_item", "%1$s %2$s (instalada: %3$s)", "%1$s %2$s (installed: %3$s)", "%1$s %2$s (instalada: %3$s)", "%1$s %2$s (installée : %3$s)", "%1$s %2$s (installiert: %3$s)"},
        {"app_size", "Atualização de app · %s", "App update · %s", "Actualización de app · %s", "Mise à jour d'app · %s", "App-Update · %s"},
        {"install", "Instalar", "Install", "Instalar", "Installer", "Installieren"},
        {"cancel", "Cancelar", "Cancel", "Cancelar", "Annuler", "Abbrechen"},
        {"confirm_fw_title", "Instalar a firmware %s?", "Install firmware %s?", "¿Instalar el firmware %s?", "Installer le firmware %s ?", "Firmware %s installieren?"},
        {"confirm_fw_msg", "Não desligue a box nem retire a alimentação durante a atualização. No fim, a box tem de ser reiniciada.", "Do not power off or unplug the box during the update. The box restarts at the end.", "No apague ni desenchufe el box durante la actualización. Al final, el box se reinicia.", "N'éteignez pas et ne débranchez pas le boîtier pendant la mise à jour. Le boîtier redémarre à la fin.", "Die Box während des Updates nicht ausschalten oder vom Strom trennen. Am Ende wird die Box neu gestartet."},
        {"confirm_app", "Instalar %1$s %2$s?", "Install %1$s %2$s?", "¿Instalar %1$s %2$s?", "Installer %1$s %2$s ?", "%1$s %2$s installieren?"},
        {"downloading", "A transferir… %1$d%% (%2$s de %3$s)", "Downloading… %1$d%% (%2$s of %3$s)", "Descargando… %1$d%% (%2$s de %3$s)", "Téléchargement… %1$d %% (%2$s sur %3$s)", "Wird heruntergeladen… %1$d %% (%2$s von %3$s)"},
        {"verifying", "A verificar…", "Verifying…", "Verificando…", "Vérification…", "Wird überprüft…"},
        {"bad_hash", "O ficheiro transferido está corrompido (tamanho ou SHA-256 diferente).", "The downloaded file is corrupted (size or SHA-256 mismatch).", "El archivo descargado está dañado (tamaño o SHA-256 distinto).", "Le fichier téléchargé est corrompu (taille ou SHA-256 différent).", "Die heruntergeladene Datei ist beschädigt (Größe oder SHA-256 stimmt nicht)."},
        {"no_space", "Espaço insuficiente (são precisos %s).", "Not enough free space (%s needed).", "Espacio insuficiente (se necesitan %s).", "Espace insuffisant (%s nécessaires).", "Nicht genug freier Speicher (%s benötigt)."},
        {"extracting", "A extrair o pacote…", "Extracting the package…", "Extrayendo el paquete…", "Extraction du paquet…", "Paket wird entpackt…"},
        {"bad_package", "Pacote inválido: %s", "Invalid package: %s", "Paquete no válido: %s", "Paquet invalide : %s", "Ungültiges Paket: %s"},
        {"applying", "A aplicar a atualização… não desligue a box.", "Applying the update… do not power off the box.", "Aplicando la actualización… no apague el box.", "Application de la mise à jour… n'éteignez pas le boîtier.", "Update wird angewendet… Box nicht ausschalten."},
        {"applied", "Atualização aplicada — reinicie agora.", "Update applied — restart now.", "Actualización aplicada: reinicie ahora.", "Mise à jour appliquée — redémarrez maintenant.", "Update angewendet – jetzt neu starten."},
        {"apply_failed", "A atualização falhou (código %d). Veja o registo abaixo.", "The update failed (code %d). See the log below.", "La actualización ha fallado (código %d). Consulte el registro abajo.", "La mise à jour a échoué (code %d). Voir le journal ci-dessous.", "Das Update ist fehlgeschlagen (Code %d). Siehe Protokoll unten."},
        {"restart", "Reiniciar agora", "Restart now", "Reiniciar ahora", "Redémarrer maintenant", "Jetzt neu starten"},
        {"restarting", "A reiniciar…", "Restarting…", "Reiniciando…", "Redémarrage…", "Neustart…"},
        {"no_root", "Root não autorizado: Magisk → Superutilizador → + → A95X Z2 Updater", "Root not granted: Magisk → Superuser → + → A95X Z2 Updater", "Root no autorizado: Magisk → Superusuario → + → A95X Z2 Updater", "Root non autorisé : Magisk → Superutilisateur → + → A95X Z2 Updater", "Root nicht erlaubt: Magisk → Superuser → + → A95X Z2 Updater"},
        {"installing_app", "A instalar %s…", "Installing %s…", "Instalando %s…", "Installation de %s…", "%s wird installiert…"},
        {"app_ok", "Instalação concluída: %s", "Installed: %s", "Instalación completada: %s", "Installation terminée : %s", "Installation abgeschlossen: %s"},
        {"app_fail", "Falha ao instalar %1$s: %2$s", "Failed to install %1$s: %2$s", "Error al instalar %1$s: %2$s", "Échec de l'installation de %1$s : %2$s", "Installation von %1$s fehlgeschlagen: %2$s"},
        {"error", "Erro: %s", "Error: %s", "Error: %s", "Erreur : %s", "Fehler: %s"},
        {"log", "Registo", "Log", "Registro", "Journal", "Protokoll"},
        {"busy", "Aguarde: há uma operação em curso.", "Please wait: an operation is in progress.", "Espere: hay una operación en curso.", "Patientez : une opération est en cours.", "Bitte warten: Ein Vorgang läuft."},
        {"popup_fw", "Nova atualização do sistema disponível: %s", "New system update available: %s", "Nueva actualización del sistema disponible: %s", "Nouvelle mise à jour du système disponible : %s", "Neues Systemupdate verfügbar: %s"},
        {"popup_app", "Nova versão disponível: %1$s %2$s", "New version available: %1$s %2$s", "Nueva versión disponible: %1$s %2$s", "Nouvelle version disponible : %1$s %2$s", "Neue Version verfügbar: %1$s %2$s"},
        {"popup_hint", "OK: abrir  ·  VOLTAR: fechar", "OK: open  ·  BACK: close", "OK: abrir  ·  ATRÁS: cerrar", "OK : ouvrir  ·  RETOUR : fermer", "OK: öffnen  ·  ZURÜCK: schließen"},
        {"auto_line", "Verificação automática a cada 6 h  ·  última verificação: %s", "Automatic check every 6 h  ·  last check: %s", "Comprobación automática cada 6 h  ·  última comprobación: %s", "Vérification automatique toutes les 6 h  ·  dernière vérification : %s", "Automatische Prüfung alle 6 Std.  ·  letzte Prüfung: %s"},
        {"never", "nunca", "never", "nunca", "jamais", "nie"},
        {"notes", "Novidades", "What's new", "Novedades", "Nouveautés", "Neuerungen"},
    };

    private static final HashMap<String, String[]> MAP = new HashMap<>();
    static {
        for (String[] r : T) {
            if (r.length != CODES.length + 1) throw new IllegalStateException("traducao incompleta: " + r[0]);
            MAP.put(r[0], r);
        }
    }

    private static int col = 2;
    private static Locale locale = Locale.ENGLISH;
    private static String code = "en";

    /** Le o idioma do sistema (chamar em onCreate). */
    static void init() {
        String c = Locale.getDefault().getLanguage();
        int i = indexOf(c);
        if (i < 0) i = 1;                         // idioma sem traducao -> ingles
        col = i + 1;
        code = CODES[i];
        locale = "pt".equals(code) ? new Locale("pt", "PT") : new Locale(code);
    }

    static int indexOf(String c) {
        for (int i = 0; i < CODES.length; i++) if (CODES[i].equals(c)) return i;
        return -1;
    }

    static String code() { return code; }

    static String s(String key) {
        String[] r = MAP.get(key);
        return r == null ? key : r[col];
    }

    static String f(String key, Object... args) {
        return String.format(locale, s(key), args);
    }

    static Locale locale() { return locale; }
}
