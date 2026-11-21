package pt.a95xz2.updater;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/**
 * So para testes (protegido com android.permission.DUMP: o adb shell tem-na, as apps nao):
 *   adb shell am broadcast -n pt.a95xz2.updater/.CheckReceiver --ez force true
 * force=true volta a mostrar o aviso mesmo que ja tenha sido mostrado.
 * demo=true (com a box ja atualizada) mostra o aviso com a firmware do manifesto, sem gravar nada:
 *   adb shell am broadcast -n pt.a95xz2.updater/.CheckReceiver --ez force true --ez demo true
 */
public class CheckReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context c, Intent i) {
        final boolean force = i.getBooleanExtra("force", false);
        final boolean demo = i.getBooleanExtra("demo", false);
        final PendingResult pr = goAsync();
        final Context app = c.getApplicationContext();
        new Thread(() -> {
            try {
                CheckJob.run(app, force, demo);
            } finally {
                pr.finish();
            }
        }, "ota-check-debug").start();
    }
}
