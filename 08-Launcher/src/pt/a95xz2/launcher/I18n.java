package pt.a95xz2.launcher;

import java.util.HashMap;
import java.util.Locale;

/**
 * Textos do launcher em varios idiomas (sem recursos: tabela em codigo, carregada uma vez).
 * Idioma: "auto" segue o idioma do sistema Android; senao pt, en, es, fr, de.
 * Para acrescentar um idioma: juntar o codigo a CODES/NAMES e uma coluna a cada linha de T.
 */
final class I18n {
    static final String[] CODES = {"pt", "en", "es", "fr", "de"};
    static final String[] NAMES = {"Português", "English", "Español", "Français", "Deutsch"};

    // chave, pt, en, es, fr, de
    private static final String[][] T = {
        {"favorites", "Favoritos", "Favorites", "Favoritos", "Favoris", "Favoriten"},
        {"apps", "Apps", "Apps", "Apps", "Applications", "Apps"},
        {"apps_hidden_shown", "Apps (a mostrar as ocultas)", "Apps (showing hidden)", "Apps (mostrando ocultas)", "Applications (masquées visibles)", "Apps (ausgeblendete sichtbar)"},
        {"empty_favs", "Prime MENU (ou OK longo) numa app para a juntar aos favoritos.", "Press MENU (or long OK) on an app to add it to favorites.", "Pulsa MENÚ (u OK largo) en una app para añadirla a favoritos.", "Appuyez sur MENU (ou OK long) sur une app pour l'ajouter aux favoris.", "MENÜ (oder lange OK) auf einer App drücken, um sie zu Favoriten hinzuzufügen."},
        {"sort_apps_prefix", "Ordenar apps: ", "Sort apps: ", "Ordenar apps: ", "Trier les apps : ", "Apps sortieren: "},
        {"most_used", "mais usadas", "most used", "más usadas", "plus utilisées", "meistgenutzt"},
        {"custom", "personalizada", "custom", "personalizado", "personnalisé", "benutzerdefiniert"},
        {"az", "A–Z", "A–Z", "A–Z", "A–Z", "A–Z"},
        {"edit_favs", "Editar favoritos", "Edit favorites", "Editar favoritos", "Modifier les favoris", "Favoriten bearbeiten"},
        {"edit_favs_hint", "OK: marcar ou desmarcar   ·   as marcadas ficam nos favoritos", "OK: select or unselect   ·   selected apps stay in favorites", "OK: marcar o desmarcar   ·   las marcadas quedan en favoritos", "OK : cocher ou décocher   ·   les apps cochées restent en favoris", "OK: aus- oder abwählen   ·   ausgewählte Apps bleiben Favoriten"},
        {"cancel", "Cancelar", "Cancel", "Cancelar", "Annuler", "Abbrechen"},
        {"save", "Guardar", "Save", "Guardar", "Enregistrer", "Speichern"},
        {"move_hint", "Setas: mover   ·   OK ou VOLTAR: terminar", "Arrows: move   ·   OK or BACK: done", "Flechas: mover   ·   OK o ATRÁS: terminar", "Flèches : déplacer   ·   OK ou RETOUR : terminer", "Pfeile: verschieben   ·   OK oder ZURÜCK: fertig"},
        {"visible_apps", "Apps visíveis: desmarcar para ocultar", "Visible apps: unselect to hide", "Apps visibles: desmarca para ocultar", "Apps visibles : décocher pour masquer", "Sichtbare Apps: abwählen zum Ausblenden"},
        {"alpha", "Alfabética (A–Z)", "Alphabetical (A–Z)", "Alfabético (A–Z)", "Alphabétique (A–Z)", "Alphabetisch (A–Z)"},
        {"by_use", "Mais usadas", "Most used", "Más usadas", "Plus utilisées", "Meistgenutzt"},
        {"manual", "Manual (mover com as setas)", "Manual (move with arrows)", "Manual (mover con las flechas)", "Manuel (déplacer avec les flèches)", "Manuell (mit Pfeilen verschieben)"},
        {"custom_long", "Personalizada (mover com as setas)", "Custom (move with arrows)", "Personalizado (mover con las flechas)", "Personnalisé (déplacer avec les flèches)", "Benutzerdefiniert (mit Pfeilen verschieben)"},
        {"sort_favs", "Ordenar favoritos", "Sort favorites", "Ordenar favoritos", "Trier les favoris", "Favoriten sortieren"},
        {"sort_apps", "Ordenar apps", "Sort apps", "Ordenar apps", "Trier les apps", "Apps sortieren"},
        {"open", "Abrir", "Open", "Abrir", "Ouvrir", "Öffnen"},
        {"move", "Mover", "Move", "Mover", "Déplacer", "Verschieben"},
        {"sort_favs_more", "Ordenar favoritos…", "Sort favorites…", "Ordenar favoritos…", "Trier les favoris…", "Favoriten sortieren…"},
        {"sort_apps_more", "Ordenar apps…", "Sort apps…", "Ordenar apps…", "Trier les apps…", "Apps sortieren…"},
        {"remove_fav", "Remover dos favoritos", "Remove from favorites", "Quitar de favoritos", "Retirer des favoris", "Aus Favoriten entfernen"},
        {"add_fav", "Juntar aos favoritos", "Add to favorites", "Añadir a favoritos", "Ajouter aux favoris", "Zu Favoriten hinzufügen"},
        {"show_in_list", "Mostrar na lista de apps", "Show in app list", "Mostrar en la lista de apps", "Afficher dans la liste", "In App-Liste anzeigen"},
        {"hide_from_list", "Ocultar da lista de apps", "Hide from app list", "Ocultar de la lista de apps", "Masquer de la liste", "Aus App-Liste ausblenden"},
        {"app_info", "Informações da app", "App info", "Información de la app", "Infos sur l'app", "App-Info"},
        {"uninstall", "Desinstalar", "Uninstall", "Desinstalar", "Désinstaller", "Deinstallieren"},
        {"show_hide_apps", "Mostrar/ocultar apps", "Show/hide apps", "Mostrar/ocultar apps", "Afficher/masquer les apps", "Apps ein-/ausblenden"},
        {"android_settings", "Definições do Android", "Android settings", "Ajustes de Android", "Paramètres Android", "Android-Einstellungen"},
        {"network", "Rede e Wi-Fi", "Network & Wi-Fi", "Red y Wi-Fi", "Réseau et Wi-Fi", "Netzwerk & WLAN"},
        {"language", "Idioma", "Language", "Idioma", "Langue", "Sprache"},
        {"lang_auto", "Automático (idioma do sistema)", "Automatic (system language)", "Automático (idioma del sistema)", "Automatique (langue du système)", "Automatisch (Systemsprache)"},
        {"lang_system", "Idioma do sistema Android…", "Android system language…", "Idioma del sistema Android…", "Langue du système Android…", "Android-Systemsprache…"},
        {"about", "Sobre", "About", "Acerca de", "À propos", "Über"},
        {"support", "Apoiar o projeto", "Support the project", "Apoyar el proyecto", "Soutenir le projet", "Projekt unterstützen"},
        {"about_keys", "OK: abrir  ·  MENU: opções da app  ·  HOME: início", "OK: open  ·  MENU: app options  ·  HOME: start", "OK: abrir  ·  MENÚ: opciones  ·  HOME: inicio", "OK : ouvrir  ·  MENU : options  ·  HOME : accueil", "OK: öffnen  ·  MENÜ: Optionen  ·  HOME: Start"},
        {"no_network", "Sem rede", "No network", "Sin red", "Pas de réseau", "Kein Netzwerk"},
        {"ethernet", "Cabo", "Ethernet", "Cable", "Câble", "Kabel"},
        {"wifi", "Wi-Fi", "Wi-Fi", "Wi-Fi", "Wi-Fi", "WLAN"},
        {"recents", "Recentes", "Recent", "Recientes", "Récents", "Zuletzt verwendet"},
        {"show_recents", "Mostrar recentes", "Show recent apps", "Mostrar recientes", "Afficher les récents", "Zuletzt verwendete anzeigen"},
        {"clear_recents", "Limpar recentes", "Clear recent apps", "Borrar recientes", "Effacer les récents", "Zuletzt verwendete löschen"},
        {"recents_cleared", "Recentes limpos", "Recent apps cleared", "Recientes borrados", "Récents effacés", "Liste gelöscht"},
        {"remove_from_recents", "Remover dos recentes", "Remove from recent", "Quitar de recientes", "Retirer des récents", "Aus „Zuletzt verwendet“ entfernen"},
        {"yes", "Sim", "Yes", "Sí", "Oui", "Ja"},
        {"no", "Não", "No", "No", "Non", "Nein"},
        {"categories", "Categorias", "Categories", "Categorías", "Catégories", "Kategorien"},
        {"new_category", "Nova categoria", "New category", "Nueva categoría", "Nouvelle catégorie", "Neue Kategorie"},
        {"category_name", "Nome da categoria", "Category name", "Nombre de la categoría", "Nom de la catégorie", "Name der Kategorie"},
        {"edit_apps", "Editar apps", "Edit apps", "Editar apps", "Modifier les apps", "Apps bearbeiten"},
        {"pick_hint", "OK: marcar ou desmarcar   ·   as marcadas ficam na categoria", "OK: select or unselect   ·   selected apps stay in the category", "OK: marcar o desmarcar   ·   las marcadas quedan en la categoría", "OK : cocher ou décocher   ·   les apps cochées restent dans la catégorie", "OK: aus- oder abwählen   ·   ausgewählte Apps bleiben in der Kategorie"},
        {"rename", "Renomear", "Rename", "Cambiar nombre", "Renommer", "Umbenennen"},
        {"move_up", "Mover para cima", "Move up", "Subir", "Monter", "Nach oben"},
        {"move_down", "Mover para baixo", "Move down", "Bajar", "Descendre", "Nach unten"},
        {"delete", "Apagar", "Delete", "Eliminar", "Supprimer", "Löschen"},
        {"delete_cat_q", "Apagar a categoria «%s»? As apps continuam instaladas.", "Delete the category “%s”? The apps stay installed.", "¿Eliminar la categoría «%s»? Las apps siguen instaladas.", "Supprimer la catégorie « %s » ? Les apps restent installées.", "Kategorie „%s“ löschen? Die Apps bleiben installiert."},
        {"add_to_cat", "Juntar a uma categoria…", "Add to a category…", "Añadir a una categoría…", "Ajouter à une catégorie…", "Zu einer Kategorie hinzufügen…"},
        {"remove_from_cat", "Remover de «%s»", "Remove from “%s”", "Quitar de «%s»", "Retirer de « %s »", "Aus „%s“ entfernen"},
        {"root_apps", "Autorizar root a uma app (Magisk)…", "Grant root to an app (Magisk)…", "Autorizar root a una app (Magisk)…", "Autoriser root pour une app (Magisk)…", "Root für eine App erlauben (Magisk)…"},
        {"grp_favs", "Favoritos", "Favorites", "Favoritos", "Favoris", "Favoriten"},
        {"grp_apps", "Apps e categorias", "Apps & categories", "Apps y categorías", "Apps et catégories", "Apps & Kategorien"},
        {"grp_custom", "Personalizar", "Customize", "Personalizar", "Personnaliser", "Anpassen"},
        {"grp_system", "Sistema", "System", "Sistema", "Système", "System"},
        {"system_update", "Atualização do sistema", "System update", "Actualización del sistema", "Mise à jour du système", "Systemupdate"},
        {"close_bg", "Fechar apps em segundo plano", "Close background apps", "Cerrar apps en segundo plano", "Fermer les apps en arrière-plan", "Hintergrund-Apps schließen"},
        {"close_app", "Fechar app", "Close app", "Cerrar app", "Fermer l'app", "App schließen"},
        {"apps_closed", "Apps em segundo plano fechadas", "Background apps closed", "Apps en segundo plano cerradas", "Apps en arrière-plan fermées", "Hintergrund-Apps geschlossen"},
        {"app_closed", "App fechada", "App closed", "App cerrada", "App fermée", "App geschlossen"},
        {"no_root_partial", "(sem root: só as apps em cache)", "(no root: cached apps only)", "(sin root: solo apps en caché)", "(sans root : apps en cache seulement)", "(ohne Root: nur zwischengespeicherte Apps)"},
        {"net_adb", "Depuração ADB por rede", "ADB debugging over network", "Depuración ADB por red", "Débogage ADB par le réseau", "ADB-Debugging über Netzwerk"},
        {"on", "Ligada", "On", "Activada", "Activé", "Ein"},
        {"off", "Desligada", "Off", "Desactivada", "Désactivé", "Aus"},
        {"need_root", "É preciso root (Magisk) para esta opção", "Root (Magisk) is required for this option", "Se necesita root (Magisk) para esta opción", "Le root (Magisk) est nécessaire pour cette option", "Für diese Option ist Root (Magisk) nötig"},
        {"launcher_opts", "Opções do launcher…", "Launcher options…", "Opciones del launcher…", "Options du launcher…", "Launcher-Optionen…"},
        {"autostart", "Abrir ao ligar a box", "Open when the box starts", "Abrir al encender el box", "Ouvrir au démarrage du boîtier", "Beim Einschalten öffnen"},
        {"none", "Nenhuma", "None", "Ninguna", "Aucune", "Keine"},
        {"screensaver", "Proteção de ecrã", "Screensaver", "Salvapantallas", "Économiseur d'écran", "Bildschirmschoner"},
        {"off", "Desligada", "Off", "Desactivado", "Désactivé", "Aus"},
        {"minutes", "%d minutos", "%d minutes", "%d minutos", "%d minutes", "%d Minuten"},
        {"export_cfg", "Exportar configuração", "Export settings", "Exportar configuración", "Exporter la configuration", "Konfiguration exportieren"},
        {"import_cfg", "Importar configuração", "Import settings", "Importar configuración", "Importer la configuration", "Konfiguration importieren"},
        {"export_ok", "Configuração exportada", "Settings exported", "Configuración exportada", "Configuration exportée", "Konfiguration exportiert"},
        {"import_ok", "Configuração importada", "Settings imported", "Configuración importada", "Configuration importée", "Konfiguration importiert"},
        {"cfg_error", "Ficheiro inválido ou erro ao ler/escrever", "Invalid file or read/write error", "Archivo no válido o error de lectura/escritura", "Fichier invalide ou erreur de lecture/écriture", "Ungültige Datei oder Lese-/Schreibfehler"},
        {"saved_to", "Configuração guardada em: ", "Settings saved to: ", "Configuración guardada en: ", "Configuration enregistrée dans : ", "Konfiguration gespeichert unter: "},
        {"date_fmt","EEEE, d 'de' MMMM", "EEEE, MMMM d", "EEEE, d 'de' MMMM", "EEEE d MMMM", "EEEE, d. MMMM"},
    };

    private static final HashMap<String, String[]> MAP = new HashMap<>();
    static {
        for (String[] r : T) {
            if (r.length != CODES.length + 1) throw new IllegalStateException("traducao incompleta: " + r[0]);
            MAP.put(r[0], r);
        }
    }

    private static int col = 1;
    private static Locale locale = new Locale("pt", "PT");

    /** pref: "auto" ou um codigo de CODES. */
    static void set(String pref) {
        String code = pref;
        if (code == null || "auto".equals(code)) code = Locale.getDefault().getLanguage();
        int i = indexOf(code);
        if (i < 0) i = 1;                         // idioma do sistema sem traducao -> ingles
        col = i + 1;
        String c = CODES[i];
        locale = "pt".equals(c) ? new Locale("pt", "PT") : new Locale(c);
    }

    static int indexOf(String code) {
        for (int i = 0; i < CODES.length; i++) if (CODES[i].equals(code)) return i;
        return -1;
    }

    static String s(String key) {
        String[] r = MAP.get(key);
        return r == null ? key : r[col];
    }

    static Locale locale() { return locale; }
}
