package pt.a95xz2.updater;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** No arranque: agenda o job de 6 h e uma verificacao ~2 min depois. */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context c, Intent i) {
        if (!Intent.ACTION_BOOT_COMPLETED.equals(i.getAction())) return;
        Ota.schedulePeriodic(c);
        Ota.scheduleOnce(c, Ota.JOB_BOOT, 2 * 60_000L);
    }
}
