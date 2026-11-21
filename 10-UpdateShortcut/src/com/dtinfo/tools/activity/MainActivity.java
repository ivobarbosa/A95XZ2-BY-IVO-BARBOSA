package com.dtinfo.tools.activity;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;

/** Reencaminha "Definicoes -> Atualizacao do sistema" para o A95X Z2 Updater. */
public class MainActivity extends Activity {
    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        try {
            Intent i = new Intent(Intent.ACTION_MAIN);
            i.setClassName("pt.a95xz2.updater", "pt.a95xz2.updater.MainActivity");
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(i);
        } catch (Exception ignored) { }
        finish();
    }
}
