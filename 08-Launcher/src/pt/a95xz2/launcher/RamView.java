package pt.a95xz2.launcher;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.view.View;

/** Indicador de memoria: anel cuja parte cheia e a RAM em uso (o resto esta livre). */
public class RamView extends View {
    private final Paint track = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint arc = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF box = new RectF();
    private float used = -1f;   // 0..1, -1 = desconhecido

    public RamView(Context c) {
        super(c);
        track.setStyle(Paint.Style.STROKE);
        track.setColor(0x40FFFFFF);
        arc.setStyle(Paint.Style.STROKE);
        arc.setStrokeCap(Paint.Cap.ROUND);
    }

    public void setUsed(float u) {
        if (Math.abs(u - used) > 0.005f) { used = u; invalidate(); }
    }

    @Override
    protected void onDraw(Canvas c) {
        float w = getWidth(), h = getHeight(), s = Math.min(w, h), sw = s * 0.2f;
        track.setStrokeWidth(sw);
        arc.setStrokeWidth(sw);
        box.set((w - s) / 2 + sw / 2, (h - s) / 2 + sw / 2, (w + s) / 2 - sw / 2, (h + s) / 2 - sw / 2);
        c.drawOval(box, track);
        if (used < 0) return;
        arc.setColor(used >= 0.85f ? 0xFFFF8A65 : 0xE6FFFFFF);
        c.drawArc(box, -90, 360 * Math.max(0.02f, used), false, arc);
    }
}
