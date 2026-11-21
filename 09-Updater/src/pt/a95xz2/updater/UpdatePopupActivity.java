package pt.a95xz2.updater;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.Window;
import android.view.WindowManager;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

/**
 * Aviso pequeno no canto inferior direito ("ha uma atualizacao"). Fecha sozinho em 12 s.
 * OK (ou toque) abre o updater; VOLTAR fecha. Nao fica nos recentes nem no historico.
 */
public class UpdatePopupActivity extends Activity {
    static final String EXTRA_TEXT = "text";
    private static final long AUTO_CLOSE = 12_000L;
    private final Handler ui = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        I18n.init();
        float dp = getResources().getDisplayMetrics().density;

        Window w = getWindow();
        w.clearFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND);
        w.setGravity(Gravity.BOTTOM | Gravity.END);
        WindowManager.LayoutParams lp = w.getAttributes();
        lp.x = Math.round(40 * dp);
        lp.y = Math.round(40 * dp);
        lp.width = WindowManager.LayoutParams.WRAP_CONTENT;
        lp.height = WindowManager.LayoutParams.WRAP_CONTENT;
        w.setAttributes(lp);

        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.HORIZONTAL);
        card.setGravity(Gravity.CENTER_VERTICAL);
        int pad = Math.round(18 * dp);
        card.setPadding(pad, pad, Math.round(26 * dp), pad);
        GradientDrawable g = new GradientDrawable();
        g.setCornerRadius(16 * dp);
        g.setColor(0xFF1A2233);   // opaco: o fundo do launcher nao deve transparecer
        g.setStroke(Math.round(2 * dp), 0x66FFFFFF);
        card.setBackground(g);

        ImageView icon = new ImageView(this);
        icon.setImageResource(R.drawable.icon);
        int is = Math.round(56 * dp);
        LinearLayout.LayoutParams ilp = new LinearLayout.LayoutParams(is, is);
        ilp.setMargins(0, 0, Math.round(18 * dp), 0);
        card.addView(icon, ilp);

        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        TextView t = new TextView(this);
        String s = getIntent().getStringExtra(EXTRA_TEXT);
        t.setText(s != null ? s : I18n.s("title"));
        t.setTextSize(19);
        t.setTextColor(Color.WHITE);
        t.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        t.setMaxWidth(Math.round(560 * dp));
        col.addView(t);
        TextView h = new TextView(this);
        h.setText(I18n.s("popup_hint"));
        h.setTextSize(14);
        h.setTextColor(0xB3FFFFFF);
        h.setPadding(0, Math.round(6 * dp), 0, 0);
        col.addView(h);
        card.addView(col);

        card.setOnClickListener(v -> open());
        setContentView(card);
        ui.postDelayed(this::finish, AUTO_CLOSE);
    }

    private void open() {
        startActivity(new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        finish();
    }

    @Override
    public boolean onKeyUp(int keyCode, KeyEvent e) {
        if (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER
                || keyCode == KeyEvent.KEYCODE_NUMPAD_ENTER || keyCode == KeyEvent.KEYCODE_BUTTON_A) {
            open();
            return true;
        }
        return super.onKeyUp(keyCode, e);
    }

    @Override
    protected void onDestroy() {
        ui.removeCallbacksAndMessages(null);
        super.onDestroy();
    }
}
