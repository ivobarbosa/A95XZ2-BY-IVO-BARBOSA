package pt.a95xz2.updater;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.ConnectivityManager;
import android.net.NetworkInfo;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.PrintWriter;
import java.util.ArrayDeque;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/**
 * A95X Z2 Updater: procura atualizacoes (manifesto assinado no GitHub), aplica deltas de
 * firmware via root (apply.sh do pacote) e atualiza apps com pm install -r.
 * Verificacao automatica de 6 em 6 h em CheckJob (aviso no canto); aqui so quando o utilizador pede.
 */
public class MainActivity extends Activity {

    private static final String INSTALL_URL = "https://github.com/ivobarbosa/A95XZ2-BY-IVO-BARBOSA/blob/main/INSTALL.md";
    // Pasta de trabalho do pacote delta (root). Recriada de cada vez.
    static final String OTA_DIR = "/data/local/tmp/a95x-ota";
    private static final String APK_TMP = "/data/local/tmp/a95x-app.apk";
    private static final int LOG_LINES = 14;
    private static final int ACCENT = 0xFF4FC3F7;

    private float dp;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private volatile boolean busy = false;

    private TextView fwLabel, status, autoLine, logView, logTitle;
    private TextView checkBtn, restartBtn;
    private ProgressBar bar;
    private LinearLayout list;
    private final ArrayDeque<String> log = new ArrayDeque<>();

    private int fwInstalled = -1;   // -1 = desconhecida

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        I18n.init();
        dp = getResources().getDisplayMetrics().density;
        setContentView(buildUi());
        fwInstalled = Ota.installedFw();
        refreshInfo();
        Ota.schedulePeriodic(this);   // idempotente: nao reinicia o periodo
        status.setText(I18n.s("hint"));
        checkBtn.requestFocus();
        // 1.3: procura logo ao abrir (Definicoes -> Atualizacao do sistema), sem ter de carregar no botao
        checkBtn.post(() -> { if (!busy) checkUpdates(); });
    }

    /** Aberta outra vez (Definicoes ou aviso) com a app ja em memoria: volta a procurar se estiver livre. */
    @Override
    protected void onNewIntent(android.content.Intent i) {
        super.onNewIntent(i);
        if (!busy) checkUpdates();
    }

    @Override
    protected void onResume() {
        super.onResume();
        refreshAuto();
    }

    /** Idioma do sistema mudou com a app aberta: reconstruir os textos (se nao estiver ocupada). */
    @Override
    public void onConfigurationChanged(android.content.res.Configuration c) {
        super.onConfigurationChanged(c);
        String before = I18n.code();
        I18n.init();
        if (!before.equals(I18n.code()) && !busy) recreate();
    }

    @Override
    protected void onDestroy() {
        io.shutdownNow();
        super.onDestroy();
    }

    @Override
    public void onBackPressed() {
        if (busy) { toast(I18n.s("busy")); return; }   // nunca sair a meio de uma atualizacao
        super.onBackPressed();
    }

    // ------------------------------------------------------------------ interface

    private int px(float v) { return Math.round(v * dp); }

    private View buildUi() {
        FrameLayout root = new FrameLayout(this);

        // Marca de agua igual a do launcher (atras do conteudo)
        TextView mark = text("A95X Z2", 120, 0x0DFFFFFF, true);
        mark.setTypeface(Typeface.create("sans-serif-black", Typeface.NORMAL));
        FrameLayout.LayoutParams mlp = new FrameLayout.LayoutParams(-2, -2, Gravity.BOTTOM | Gravity.END);
        mlp.setMargins(0, 0, px(40), px(10));
        root.addView(mark, mlp);

        ScrollView scroll = new ScrollView(this);
        root.addView(scroll, new FrameLayout.LayoutParams(-1, -1));
        scroll.setFillViewport(true);
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setPadding(px(56), px(32), px(56), px(40));
        col.setClipChildren(false);
        scroll.addView(col);

        // Titulo a esquerda, versao da firmware pequena a direita na mesma linha
        LinearLayout head = new LinearLayout(this);
        head.setOrientation(LinearLayout.HORIZONTAL);
        head.setGravity(Gravity.CENTER_VERTICAL);
        head.setPadding(0, 0, 0, px(22));
        TextView title = text(I18n.s("title"), 32, Color.WHITE, true);
        head.addView(title, new LinearLayout.LayoutParams(0, -2, 1f));
        fwLabel = text("", 16, 0xB3FFFFFF, false);
        head.addView(fwLabel);
        col.addView(head);

        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setPadding(px(6), px(6), px(6), px(6));
        row.setClipToPadding(false);   // o botao focado cresce 6%: nao cortar o contorno
        row.setClipChildren(false);
        checkBtn = button(I18n.s("check"), v -> checkUpdates());
        row.addView(checkBtn);
        restartBtn = button(I18n.s("restart"), v -> restart());
        restartBtn.setVisibility(View.GONE);
        LinearLayout.LayoutParams rlp = new LinearLayout.LayoutParams(-2, -2);
        rlp.setMargins(px(20), 0, 0, 0);
        row.addView(restartBtn, rlp);
        col.addView(row);

        status = text("", 18, Color.WHITE, false);
        status.setPadding(0, px(14), 0, px(8));
        col.addView(status);

        autoLine = text("", 14, 0x80FFFFFF, false);
        autoLine.setPadding(0, 0, 0, px(8));
        col.addView(autoLine);

        bar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        bar.setMax(1000);
        bar.setVisibility(View.GONE);
        col.addView(bar, new LinearLayout.LayoutParams(-1, px(10)));

        list = new LinearLayout(this);
        list.setOrientation(LinearLayout.VERTICAL);
        list.setPadding(0, px(6), 0, 0);
        col.addView(list);

        logTitle = text(I18n.s("log"), 15, 0x99FFFFFF, true);
        logTitle.setPadding(0, px(16), 0, px(4));
        logTitle.setVisibility(View.GONE);
        col.addView(logTitle);
        logView = text("", 13, 0xFFB0BEC5, false);
        logView.setTypeface(Typeface.MONOSPACE);
        logView.setPadding(px(12), px(8), px(12), px(8));
        GradientDrawable lg = new GradientDrawable();
        lg.setCornerRadius(px(8));
        lg.setColor(0x40000000);
        logView.setBackground(lg);
        logView.setVisibility(View.GONE);
        col.addView(logView, new LinearLayout.LayoutParams(-1, -2));
        return root;
    }

    private TextView text(String s, float sp, int color, boolean bold) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(sp);
        t.setTextColor(color);
        if (bold) t.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        return t;
    }

    /** Botao focavel: foco = aumenta + contorno branco (como os cartoes do launcher). */
    private TextView button(String s, View.OnClickListener click) {
        TextView t = text(s, 18, Color.WHITE, true);
        t.setFocusable(true);
        t.setClickable(true);
        t.setGravity(Gravity.CENTER);
        t.setPadding(px(26), px(12), px(26), px(12));
        GradientDrawable g = new GradientDrawable();
        g.setCornerRadius(px(10));
        g.setColor(0x26FFFFFF);
        t.setBackground(g);
        t.setOnFocusChangeListener((v, f) -> {
            v.animate().scaleX(f ? 1.06f : 1f).scaleY(f ? 1.06f : 1f).setDuration(130).start();
            g.setStroke(f ? px(3) : 0, Color.WHITE);
            g.setColor(f ? 0x40FFFFFF : 0x26FFFFFF);
        });
        t.setOnClickListener(v -> {
            if (busy) { toast(I18n.s("busy")); return; }
            click.onClick(v);
        });
        return t;
    }

    private void toast(String s) { Toast.makeText(this, s, Toast.LENGTH_LONG).show(); }

    private AlertDialog.Builder dialog() {
        return new AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert);
    }

    private void setStatus(String s, boolean error) {
        ui.post(() -> {
            status.setText(s);
            status.setTextColor(error ? 0xFFFF8A80 : Color.WHITE);
        });
    }

    private void setBusy(boolean b) {
        busy = b;
        ui.post(() -> {
            if (b) getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            else getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            if (!b) bar.setVisibility(View.GONE);
        });
    }

    private void progress(long done, long total) {
        ui.post(() -> {
            bar.setVisibility(View.VISIBLE);
            if (total > 0) {
                bar.setIndeterminate(false);
                bar.setProgress((int) Math.min(1000, done * 1000 / total));
            } else {
                bar.setIndeterminate(true);
            }
        });
    }

    private void indeterminate() {
        ui.post(() -> { bar.setVisibility(View.VISIBLE); bar.setIndeterminate(true); });
    }

    private void clearLog() {
        synchronized (log) { log.clear(); }
        ui.post(() -> { logView.setText(""); logView.setVisibility(View.GONE); logTitle.setVisibility(View.GONE); });
    }

    /** Junta uma linha ao registo (mostra so as ultimas LOG_LINES). Thread-safe. */
    private void logLine(String l) {
        final String txt;
        synchronized (log) {
            log.addLast(l);
            while (log.size() > LOG_LINES) log.removeFirst();
            StringBuilder sb = new StringBuilder();
            for (String s : log) { if (sb.length() > 0) sb.append('\n'); sb.append(s); }
            txt = sb.toString();
        }
        ui.post(() -> {
            logTitle.setVisibility(View.VISIBLE);
            logView.setVisibility(View.VISIBLE);
            logView.setText(txt);
        });
    }

    static String size(long b) {
        if (b >= 1024L * 1024 * 1024) return String.format(I18n.locale(), "%.2f GB", b / 1073741824.0);
        if (b >= 1024L * 1024) return String.format(I18n.locale(), "%.1f MB", b / 1048576.0);
        if (b >= 1024) return String.format(I18n.locale(), "%.0f KB", b / 1024.0);
        return b + " B";
    }

    // ------------------------------------------------------------------ versoes instaladas

    private String fwName(int v) { return v > 0 ? "v" + v : I18n.s("unknown"); }

    private PackageInfo pkgInfo(String pkg) {
        try {
            return getPackageManager().getPackageInfo(pkg, 0);
        } catch (PackageManager.NameNotFoundException e) {
            return null;
        }
    }

    private void refreshInfo() {
        fwLabel.setText(I18n.s("firmware") + " " + fwName(fwInstalled));
        refreshAuto();
    }

    /** "Verificacao automatica a cada 6 h · ultima verificacao: <data>" */
    private void refreshAuto() {
        if (autoLine == null) return;
        long t = Ota.prefs(this).getLong(Ota.P_LAST, 0);
        String when = t == 0 ? I18n.s("never")
                : java.text.DateFormat.getDateTimeInstance(java.text.DateFormat.SHORT, java.text.DateFormat.SHORT,
                        I18n.locale()).format(new java.util.Date(t));
        autoLine.setText(I18n.f("auto_line", when));
    }

    // ------------------------------------------------------------------ manifesto

    private boolean online() {
        ConnectivityManager cm = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
        @SuppressWarnings("deprecation") NetworkInfo ni = cm == null ? null : cm.getActiveNetworkInfo();
        return ni != null && ni.isConnected();
    }

    private void checkUpdates() {
        list.removeAllViews();
        clearLog();
        if (!online()) { setStatus(I18n.s("no_network"), true); return; }
        setStatus(I18n.s("checking"), false);
        setBusy(true);
        indeterminate();
        io.execute(() -> {
            try {
                JSONObject m;
                try {
                    m = Ota.fetch(MainActivity.this);
                } catch (Ota.NoInfo e) {
                    setStatus(I18n.s("no_info"), false);
                    return;
                } catch (Ota.BadSig e) {
                    setStatus(I18n.s("sig_error"), true);
                    return;
                } catch (Ota.BadManifest e) {
                    setStatus(I18n.f("bad_manifest", e.getMessage()), true);
                    return;
                }
                ui.post(() -> showManifest(m));
            } catch (Exception e) {
                setStatus(I18n.f("net_error", msg(e)), true);
            } finally {
                setBusy(false);
                ui.post(this::refreshAuto);
            }
        });
    }

    private static String msg(Throwable e) {
        String s = e.getMessage();
        return s == null ? e.getClass().getSimpleName() : s;
    }

    private String notes(JSONObject fw) {
        JSONObject n = fw.optJSONObject("notes");
        if (n == null) return "";
        String s = n.optString(I18n.code(), "");
        if (s.isEmpty()) s = n.optString("en", "");
        return s;
    }

    /** Mostra as entradas aplicaveis (UI thread). */
    @SuppressWarnings("deprecation")
    private void showManifest(JSONObject m) {
        list.removeAllViews();
        int count = 0;
        View firstBtn = null;

        JSONObject fw = m.optJSONObject("firmware");
        if (fw != null) {
            int ver = fw.optInt("version", 0);
            String name = fw.optString("name", "v" + ver);
            if (ver > 0 && (fwInstalled < 0 || ver > fwInstalled)) {
                JSONObject delta = null;
                JSONArray ds = fw.optJSONArray("deltas");
                if (fwInstalled > 0 && ds != null) {
                    for (int i = 0; i < ds.length(); i++) {
                        JSONObject d = ds.optJSONObject(i);
                        if (d != null && d.optInt("from", -1) == fwInstalled) { delta = d; break; }
                    }
                }
                String head = I18n.f("fw_item", name, fwName(fwInstalled));
                String nt = notes(fw);
                if (delta != null) {
                    final JSONObject d = delta;
                    View b = entry(head, I18n.f("delta", size(d.optLong("size"))), nt,
                            v -> confirmFirmware(name, ver, d));
                    if (firstBtn == null) firstBtn = b;
                } else {
                    JSONObject full = fw.optJSONObject("full");
                    long sz = full == null ? 0 : full.optLong("size");
                    entry(head, I18n.f("full_only", sz > 0 ? size(sz) : "?", INSTALL_URL), nt, null);
                }
                count++;
            }
        }

        JSONArray apps = m.optJSONArray("apps");
        if (apps != null) {
            for (int i = 0; i < apps.length(); i++) {
                JSONObject a = apps.optJSONObject(i);
                if (a == null) continue;
                String pkg = a.optString("package", "");
                PackageInfo pi = pkg.isEmpty() ? null : pkgInfo(pkg);
                if (pi == null || pi.versionCode >= a.optInt("versionCode", 0)) continue;   // so instaladas e mais antigas
                String label = String.valueOf(pi.applicationInfo.loadLabel(getPackageManager()));
                View b = entry(I18n.f("app_item", label, a.optString("versionName", "?"), pi.versionName),
                        I18n.f("app_size", size(a.optLong("size"))), "",
                        v -> confirmApp(label, a));
                if (firstBtn == null) firstBtn = b;
                count++;
            }
        }

        setStatus(count == 0 ? I18n.s("up_to_date") : I18n.f("found_n", count), false);
        if (firstBtn != null) firstBtn.requestFocus();
    }

    /** Linha da lista: titulo, detalhe, notas e (se houver accao) botao Instalar. Devolve o botao. */
    private View entry(String head, String detail, String notes, View.OnClickListener onInstall) {
        // 1.1: botao por baixo do texto (alinhado a esquerda): a direita ficava fora do ecra em TVs com overscan
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(px(22), px(14), px(22), px(16));
        GradientDrawable g = new GradientDrawable();
        g.setCornerRadius(px(10));
        g.setColor(0x1AFFFFFF);
        box.setBackground(g);
        box.setClipToPadding(false);
        box.setClipChildren(false);

        LinearLayout txt = new LinearLayout(this);
        txt.setOrientation(LinearLayout.VERTICAL);
        txt.addView(text(head, 19, Color.WHITE, true));
        TextView d = text(detail, 15, 0xCCFFFFFF, false);
        d.setPadding(0, px(4), 0, 0);
        txt.addView(d);
        if (notes != null && !notes.isEmpty()) {
            TextView n = text(I18n.s("notes") + ": " + notes, 15, ACCENT, false);
            n.setPadding(0, px(6), 0, 0);
            txt.addView(n);
        }
        box.addView(txt, new LinearLayout.LayoutParams(-1, -2));

        View btn = null;
        if (onInstall != null) {
            btn = button(I18n.s("install"), onInstall);
            LinearLayout.LayoutParams blp = new LinearLayout.LayoutParams(-2, -2);
            blp.setMargins(px(4), px(12), 0, px(2));
            box.addView(btn, blp);
        }
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2);
        lp.setMargins(0, px(10), px(24), 0);
        list.addView(box, lp);
        return btn;
    }

    // ------------------------------------------------------------------ firmware (delta)

    private void confirmFirmware(String name, int to, JSONObject d) {
        dialog().setTitle(I18n.f("confirm_fw_title", name))
                .setMessage(I18n.s("confirm_fw_msg") + "\n\n" + I18n.f("delta", size(d.optLong("size"))))
                .setNegativeButton(I18n.s("cancel"), null)
                .setPositiveButton(I18n.s("install"), (x, w) -> installFirmware(to, d))
                .show();
    }

    private void installFirmware(int to, JSONObject d) {
        final String url = d.optString("url", "");
        final long sz = d.optLong("size", 0);
        final String sha = d.optString("sha256", "").toLowerCase();
        final int from = fwInstalled;
        clearLog();
        setBusy(true);
        io.execute(() -> {
            File zip = new File(getCacheDir(), "ota.zip");
            File work = new File(getFilesDir(), "ota");
            try {
                if (!Root.available()) { setStatus(I18n.s("no_root"), true); return; }
                if (sz <= 0 || sha.length() != 64) throw new IOException("size/sha256");
                long need = sz * 2 + 32L * 1024 * 1024;   // zip + extraido + folga
                if (getCacheDir().getUsableSpace() < need) { setStatus(I18n.f("no_space", size(need)), true); return; }

                download(url, zip, sz, sha);
                if (!zip.exists()) return;   // erro ja mostrado

                setStatus(I18n.s("extracting"), false);
                indeterminate();
                rmrf(work);
                try {
                    unzip(zip, work);
                    if (!new File(work, "apply.sh").isFile()) throw new IOException("apply.sh?");
                } catch (IOException e) {
                    rmrf(work);
                    setStatus(I18n.f("bad_package", msg(e)), true);
                    return;
                } finally {
                    zip.delete();
                }

                // Passa a pasta para /data/local/tmp/a95x-ota (mesmo sistema de ficheiros: mv e instantaneo).
                String D = Root.q(OTA_DIR);
                String prep = "rm -rf " + D + " && (mv " + Root.q(work.getAbsolutePath()) + " " + D
                        + " || cp -r " + Root.q(work.getAbsolutePath()) + " " + D + ")"
                        + " && chown -R 0:0 " + D + " && chmod -R go-rwx " + D
                        + " && (restorecon -R " + D + " 2>/dev/null; true)";
                int rc = Root.run(prep, this::logLine);
                rmrf(work);
                if (rc != 0) { setStatus(I18n.f("apply_failed", rc), true); return; }

                setStatus(I18n.s("applying"), false);
                logLine("$ sh " + OTA_DIR + "/apply.sh " + OTA_DIR);
                final PrintWriter full = new PrintWriter(new FileWriter(new File(getFilesDir(), "last-apply.log")));
                String cmd = "export A95X_FROM=" + from + " A95X_TO=" + to + "; cd " + D
                        + " && exec sh " + Root.q(OTA_DIR + "/apply.sh") + " " + D;
                try {
                    rc = Root.run(cmd, l -> { logLine(l); full.println(l); });
                    full.println("exit=" + rc);
                } finally {
                    full.close();
                }
                if (rc == 0) {
                    setStatus(I18n.s("applied"), false);
                    ui.post(() -> { restartBtn.setVisibility(View.VISIBLE); list.removeAllViews(); restartBtn.requestFocus(); });
                } else {
                    setStatus(I18n.f("apply_failed", rc), true);
                }
            } catch (Exception e) {
                setStatus(I18n.f("error", msg(e)), true);
            } finally {
                zip.delete();
                setBusy(false);
            }
        });
    }

    /** Transfere e verifica tamanho + sha256; em erro mostra-o e apaga o ficheiro. Corre em background. */
    private void download(String url, File out, long sz, String sha) throws IOException {
        out.delete();
        try {
            Net.download(url, out, sz, (done, total) -> {
                progress(done, total);
                int pct = total > 0 ? (int) (done * 100 / total) : 0;
                setStatus(I18n.f("downloading", pct, size(done), size(total)), false);
            });
        } catch (IOException e) {
            out.delete();
            setStatus(I18n.f("net_error", msg(e)), true);
            return;
        }
        setStatus(I18n.s("verifying"), false);
        indeterminate();
        if (out.length() != sz || !Net.sha256(out).equals(sha)) {
            out.delete();
            setStatus(I18n.s("bad_hash"), true);
        }
    }

    /** Extrai o zip, recusando caminhos fora da pasta (zip slip). */
    private static void unzip(File zip, File dir) throws IOException {
        String base = dir.getCanonicalPath() + File.separator;
        if (!dir.mkdirs() && !dir.isDirectory()) throw new IOException("mkdir");
        try (ZipInputStream zin = new ZipInputStream(new java.io.FileInputStream(zip))) {
            ZipEntry e;
            byte[] buf = new byte[65536];
            while ((e = zin.getNextEntry()) != null) {
                File f = new File(dir, e.getName());
                if (!f.getCanonicalPath().startsWith(base)) throw new IOException("caminho invalido: " + e.getName());
                if (e.isDirectory()) { f.mkdirs(); continue; }
                f.getParentFile().mkdirs();
                try (OutputStream os = new FileOutputStream(f)) {
                    int n;
                    while ((n = zin.read(buf)) > 0) os.write(buf, 0, n);
                }
            }
        }
    }

    private static void rmrf(File f) {
        File[] c = f.listFiles();
        if (c != null) for (File x : c) rmrf(x);
        f.delete();
    }

    private void restart() {
        setStatus(I18n.s("restarting"), false);
        io.execute(() -> {
            try {
                int rc = Root.run("setprop sys.powerctl reboot", this::logLine);
                if (rc != 0) setStatus(I18n.s("no_root"), true);
            } catch (IOException e) {
                setStatus(I18n.s("no_root"), true);
            }
        });
    }

    // ------------------------------------------------------------------ apps

    private void confirmApp(String label, JSONObject a) {
        dialog().setTitle(I18n.f("confirm_app", label, a.optString("versionName", "")))
                .setMessage(I18n.f("app_size", size(a.optLong("size"))))
                .setNegativeButton(I18n.s("cancel"), null)
                .setPositiveButton(I18n.s("install"), (x, w) -> installApp(label, a))
                .show();
    }

    @SuppressWarnings("deprecation")
    private void installApp(String label, JSONObject a) {
        final String pkg = a.optString("package", "");
        final String url = a.optString("url", "");
        final long sz = a.optLong("size", 0);
        final String sha = a.optString("sha256", "").toLowerCase();
        clearLog();
        setBusy(true);
        io.execute(() -> {
            File apk = new File(getCacheDir(), "app.apk");
            try {
                if (!Root.available()) { setStatus(I18n.s("no_root"), true); return; }
                if (sz <= 0 || sha.length() != 64) throw new IOException("size/sha256");
                download(url, apk, sz, sha);
                if (!apk.exists()) return;
                // O APK tem de ser do pacote anunciado.
                PackageInfo pi = getPackageManager().getPackageArchiveInfo(apk.getAbsolutePath(), 0);
                if (pi == null || !pkg.equals(pi.packageName)) {
                    setStatus(I18n.f("bad_package", pi == null ? "apk?" : pi.packageName), true);
                    return;
                }
                setStatus(I18n.f("installing_app", label), false);
                indeterminate();
                String T = Root.q(APK_TMP);
                final StringBuilder out = new StringBuilder();
                int rc = Root.run("cp " + Root.q(apk.getAbsolutePath()) + " " + T + " && chmod 644 " + T
                        + " && pm install -r " + T + "; r=$?; rm -f " + T + "; exit $r",
                        l -> { logLine(l); out.append(l).append('\n'); });
                if (rc == 0 && out.toString().contains("Success")) {
                    setStatus(I18n.f("app_ok", label), false);
                    ui.post(() -> { refreshInfo(); list.removeAllViews(); checkBtn.requestFocus(); });
                } else {
                    setStatus(I18n.f("app_fail", label, out.toString().trim()), true);
                }
            } catch (Exception e) {
                setStatus(I18n.f("error", msg(e)), true);
            } finally {
                apk.delete();
                setBusy(false);
            }
        });
    }
}
