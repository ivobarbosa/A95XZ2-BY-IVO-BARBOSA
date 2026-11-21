package pt.a95xz2.launcher;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.view.View;

/** Barras de sinal desenhadas em Canvas (sem recursos). -1 sem rede, 0..4 Wi-Fi, 5 cabo. */
public class SignalView extends View {
    private final Paint on = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint off = new Paint(Paint.ANTI_ALIAS_FLAG);
    private int level = -1;

    public SignalView(Context c) {
        super(c);
        on.setColor(0xE6FFFFFF);
        off.setColor(0x40FFFFFF);
    }

    public void setLevel(int l) {
        if (l != level) { level = l; invalidate(); }
    }

    @Override
    protected void onDraw(Canvas c) {
        float w = getWidth(), h = getHeight();
        if (level == 5) {   // cabo: um bloco cheio
            c.drawRoundRect(w * 0.15f, h * 0.25f, w * 0.85f, h, 3, 3, on);
            return;
        }
        int bars = 4;
        float gap = w * 0.08f, bw = (w - gap * (bars - 1)) / bars;
        for (int i = 0; i < bars; i++) {
            float x = i * (bw + gap), top = h - h * (i + 1) / bars;
            c.drawRoundRect(x, top, x + bw, h, 2, 2, (level > i) ? on : off);
        }
    }
}
