package pt.a95xz2.launcher;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.view.View;

/** Botao redondo com uma roda dentada desenhada em Canvas (sem recursos nem fontes de icones). */
public class GearView extends View {
    private final Paint bg = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint fg = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint hole = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path gear = new Path();

    public GearView(Context c) {
        super(c);
        setFocusable(true);
        setClickable(true);
        setOnFocusChangeListener((v, f) -> {
            animate().scaleX(f ? 1.1f : 1f).scaleY(f ? 1.1f : 1f).setDuration(120).start();
            invalidate();
        });
    }

    @Override
    protected void onSizeChanged(int w, int h, int ow, int oh) {
        gear.reset();
        float cx = w / 2f, cy = h / 2f, r = Math.min(w, h) * 0.26f, rt = r * 1.32f;
        int teeth = 8;
        for (int i = 0; i < teeth * 4; i++) {
            double a = Math.PI * 2 * i / (teeth * 4);
            float rr = (i % 4 == 1 || i % 4 == 2) ? rt : r;
            float x = cx + (float) (Math.cos(a) * rr), y = cy + (float) (Math.sin(a) * rr);
            if (i == 0) gear.moveTo(x, y); else gear.lineTo(x, y);
        }
        gear.close();
    }

    @Override
    protected void onDraw(Canvas c) {
        boolean f = isFocused();
        float w = getWidth(), h = getHeight();
        bg.setColor(f ? 0xFFFFFFFF : 0x1FFFFFFF);
        c.drawCircle(w / 2f, h / 2f, Math.min(w, h) / 2f, bg);
        fg.setColor(f ? 0xFF101826 : 0xCCFFFFFF);
        c.drawPath(gear, fg);
        hole.setColor(f ? 0xFFFFFFFF : 0xFF141B28);
        c.drawCircle(w / 2f, h / 2f, Math.min(w, h) * 0.11f, hole);
    }
}
