package pt.a95xz2.updater;

import android.app.job.JobInfo;
import android.app.job.JobScheduler;
import android.content.ComponentName;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.os.Build;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;

/**
 * Logica partilhada pela interface e pela verificacao automatica: manifesto assinado,
 * versao de firmware instalada, lista do que ha para atualizar e agendamento dos jobs.
 */
final class Ota {
    static final String BASE = "https://raw.githubusercontent.com/ivobarbosa/A95XZ2-BY-IVO-BARBOSA/main/updates/";
    static final String MANIFEST_URL = BASE + "updates.json";
    static final String SIG_URL = BASE + "updates.json.sig";
    static final String RELEASE_FILE = "/system/etc/a95xz2-release";

    // Jobs (cmd jobscheduler run -f pt.a95xz2.updater <id>)
    static final int JOB_PERIODIC = 6001;   // de 6 em 6 h, persistente
    static final int JOB_BOOT = 6002;       // uma vez, ~2 min depois de arrancar
    static final int JOB_RETRY = 6003;      // uma vez, 30 min depois (video a tocar / ecra desligado)
    static final long PERIOD = 6 * 3600_000L;

    static final String PREFS = "ota";
    static final String P_LAST = "last_check";      // ms da ultima verificacao concluida
    static final String P_NOTIFIED = "notified";    // chaves ja avisadas: fw6, app:pkg:vc

    /** Manifesto ainda nao publicado (404). */
    static final class NoInfo extends IOException { NoInfo() { super("404"); } }
    /** Assinatura em falta ou invalida. */
    static final class BadSig extends IOException { BadSig() { super("assinatura"); } }
    /** JSON invalido ou schema desconhecido. */
    static final class BadManifest extends IOException { BadManifest(String m) { super(m); } }

    /** O que ha para atualizar (firmware primeiro, depois apps). */
    static final class Item {
        String key;          // fw6 | app:pkg:vc
        boolean firmware;
        String name;         // v6 | versionName
        String label;        // nome da app (so apps)
    }

    /** Transfere e verifica updates.json + .sig. Grava a hora da verificacao (tambem no 404). */
    static JSONObject fetch(Context c) throws IOException {
        byte[] json;
        try {
            json = Net.get(MANIFEST_URL, 1024 * 1024);
        } catch (Net.HttpError e) {
            if (e.code == 404) { markChecked(c); throw new NoInfo(); }
            throw e;
        }
        byte[] sig;
        try {
            sig = Net.get(SIG_URL, 16 * 1024);
        } catch (Net.HttpError e) {
            if (e.code == 404) throw new BadSig();
            throw e;
        }
        byte[] pub;
        try (InputStream in = c.getResources().openRawResource(R.raw.ota_pub)) {
            pub = Net.readAll(in);
        }
        if (!Net.verify(json, sig, pub)) throw new BadSig();
        JSONObject m;
        try {
            m = new JSONObject(new String(json, "UTF-8"));
        } catch (Exception e) {
            throw new BadManifest(String.valueOf(e.getMessage()));
        }
        if (m.optInt("schema", 0) != 1) throw new BadManifest("schema " + m.opt("schema"));
        markChecked(c);
        return m;
    }

    static void markChecked(Context c) {
        prefs(c).edit().putLong(P_LAST, System.currentTimeMillis()).apply();
    }

    static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    /** Nome publico da firmware instalada (name= do ficheiro de versao, ex. "1.0"); null se nao houver. */
    static String installedFwName() {
        File f = new File(RELEASE_FILE);
        if (!f.canRead()) return null;
        try (BufferedReader r = new BufferedReader(new FileReader(f))) {
            String l;
            while ((l = r.readLine()) != null) {
                l = l.trim();
                if (l.startsWith("name=")) return l.substring(5).trim();
            }
        } catch (Exception ignored) { }
        return null;
    }

    /** Le version= de /system/etc/a95xz2-release; sem ficheiro: v4 se o modelo for A95X Z2. */
    static int installedFw() {
        File f = new File(RELEASE_FILE);
        if (f.canRead()) {
            try (BufferedReader r = new BufferedReader(new FileReader(f))) {
                String l;
                while ((l = r.readLine()) != null) {
                    l = l.trim();
                    if (l.startsWith("version=")) return Integer.parseInt(l.substring(8).trim());
                }
            } catch (Exception ignored) { }
            return -1;
        }
        return "A95X Z2".equals(Build.MODEL) ? 4 : -1;
    }

    /** Entradas aplicaveis a esta box (para o aviso automatico). */
    @SuppressWarnings("deprecation")
    static ArrayList<Item> pending(Context c, JSONObject m) {
        ArrayList<Item> out = new ArrayList<>();
        int inst = installedFw();
        JSONObject fw = m.optJSONObject("firmware");
        if (fw != null) {
            int ver = fw.optInt("version", 0);
            if (ver > 0 && (inst < 0 || ver > inst)) {
                Item it = new Item();
                it.key = "fw" + ver;
                it.firmware = true;
                it.name = fw.optString("name", "v" + ver);
                out.add(it);
            }
        }
        JSONArray apps = m.optJSONArray("apps");
        PackageManager pm = c.getPackageManager();
        if (apps != null) {
            for (int i = 0; i < apps.length(); i++) {
                JSONObject a = apps.optJSONObject(i);
                if (a == null) continue;
                String pkg = a.optString("package", "");
                int vc = a.optInt("versionCode", 0);
                PackageInfo pi;
                try { pi = pm.getPackageInfo(pkg, 0); } catch (PackageManager.NameNotFoundException e) { continue; }
                if (pi.versionCode >= vc) continue;
                Item it = new Item();
                it.key = "app:" + pkg + ":" + vc;
                it.name = a.optString("versionName", String.valueOf(vc));
                it.label = String.valueOf(pi.applicationInfo.loadLabel(pm));
                out.add(it);
            }
        }
        return out;
    }

    // ------------------------------------------------------------------ agendamento

    private static JobInfo.Builder job(Context c, int id) {
        return new JobInfo.Builder(id, new ComponentName(c, CheckJob.class))
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY);
    }

    /** Job periodico de 6 h (so agenda se ainda nao existir, para nao reiniciar o periodo). */
    static void schedulePeriodic(Context c) {
        JobScheduler js = c.getSystemService(JobScheduler.class);
        if (js == null || js.getPendingJob(JOB_PERIODIC) != null) return;
        js.schedule(job(c, JOB_PERIODIC).setPeriodic(PERIOD).setPersisted(true).build());
    }

    /** Verificacao unica daqui a delayMs (arranque: 2 min; nova tentativa: 30 min). */
    static void scheduleOnce(Context c, int id, long delayMs) {
        JobScheduler js = c.getSystemService(JobScheduler.class);
        if (js == null) return;
        js.schedule(job(c, id).setMinimumLatency(delayMs).build());
    }
}
