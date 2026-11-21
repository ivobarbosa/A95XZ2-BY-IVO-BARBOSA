package pt.a95xz2.updater;

import android.app.job.JobParameters;
import android.app.job.JobService;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.media.AudioManager;
import android.os.PowerManager;
import android.provider.Settings;
import android.util.Log;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.Set;

/**
 * Verificacao automatica (JobScheduler). Se houver algo novo ainda nao avisado, mostra o
 * aviso no canto (UpdatePopupActivity). Com video/audio a tocar ou ecra desligado, adia 30 min.
 */
public class CheckJob extends JobService {
    static final String TAG = "A95XZ2Updater";

    @Override
    public boolean onStartJob(JobParameters p) {
        final Context c = getApplicationContext();
        new Thread(() -> {
            try {
                run(c, false, false);
            } finally {
                jobFinished(p, false);
            }
        }, "ota-check").start();
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters p) { return false; }

    /**
     * force: ignora "ja avisado" e o video a tocar (para testes via adb).
     * demo: se nada estiver pendente, mostra na mesma o aviso com a firmware do manifesto
     * (so testes: a box ja na ultima versao). Nunca grava "avisado". Corre em background.
     */
    static void run(Context c, boolean force, boolean demo) {
        I18n.init();
        JSONObject m;
        try {
            m = Ota.fetch(c);
        } catch (Exception e) {
            Log.i(TAG, "verificacao: " + e);
            return;
        }
        ArrayList<Ota.Item> items = Ota.pending(c, m);
        SharedPreferences sp = Ota.prefs(c);
        Set<String> done = new HashSet<>(sp.getStringSet(Ota.P_NOTIFIED, new HashSet<>()));
        Ota.Item show = null;
        for (Ota.Item it : items) if (force || !done.contains(it.key)) { show = it; break; }
        if (show == null && demo) {
            JSONObject fw = m.optJSONObject("firmware");
            show = new Ota.Item();
            show.key = "demo";
            show.firmware = true;
            show.name = fw == null ? "?" : fw.optString("name", "v" + fw.optInt("version"));
            items.add(show);
            force = true;
        }
        Log.i(TAG, "verificacao: " + items.size() + " pendentes, aviso=" + (show == null ? "-" : show.key));
        if (show == null) return;

        PowerManager pw = (PowerManager) c.getSystemService(Context.POWER_SERVICE);
        AudioManager am = (AudioManager) c.getSystemService(Context.AUDIO_SERVICE);
        boolean screenOn = pw == null || pw.isInteractive();
        boolean playing = am != null && am.isMusicActive();
        if (!screenOn || (playing && !force)) {
            Log.i(TAG, "aviso adiado (ecra=" + screenOn + ", a tocar=" + playing + ")");
            Ota.scheduleOnce(c, Ota.JOB_RETRY, 30 * 60_000L);
            return;
        }

        // Android 10 so deixa abrir actividades em background com "mostrar sobre outras apps".
        if (!Settings.canDrawOverlays(c)) {
            try {
                Root.run("appops set " + c.getPackageName() + " SYSTEM_ALERT_WINDOW allow", null);
            } catch (Exception e) {
                Log.w(TAG, "appops: " + e);
            }
        }

        String text = show.firmware ? I18n.f("popup_fw", show.name) : I18n.f("popup_app", show.label, show.name);
        int more = 0;
        for (Ota.Item it : items) if (it != show && (force || !done.contains(it.key))) more++;
        if (more > 0) text += "  (+" + more + ")";
        Intent i = new Intent(c, UpdatePopupActivity.class)
                .putExtra(UpdatePopupActivity.EXTRA_TEXT, text)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_NO_ANIMATION);
        try {
            c.startActivity(i);
        } catch (Exception e) {
            Log.w(TAG, "aviso: " + e);
            return;
        }
        if (demo) return;
        for (Ota.Item it : items) done.add(it.key);
        sp.edit().putStringSet(Ota.P_NOTIFIED, done).apply();
    }
}
