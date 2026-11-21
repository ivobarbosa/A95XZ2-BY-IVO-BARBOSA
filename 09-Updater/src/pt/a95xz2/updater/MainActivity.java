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
 * Sem servicos nem polling: so faz rede quando o utilizador pede.
 */
public class MainActivity extends Activity {

    private static final String BASE = "https://raw.githubusercontent.com/ivobarbosa/A95XZ2-BY-IVO-BARBOSA/main/updates/";
    private static final String MANIFEST_URL = BASE + "updates.json";
    private static final String SIG_URL = BASE + "updates.json.sig";
    private static final String INSTALL_URL = "https://github.com/ivobarbosa/A95XZ2-BY-IVO-BARBOSA/blob/main/INSTALL.md";
    private static final String RELEASE_FILE = "/system/etc/a95xz2-release";
    private static final String LAUNCHER_PKG = "pt.a95xz2.launcher";
    // Pasta de trabalho do pacote delta (root). Recriada de cada vez.
    static final String OTA_DIR = "/data/local/tmp/a95x-ota";
    private static final String APK_TMP = "/data/local/tmp/a95x-app.apk";
    private static final int LOG_LINES = 14;
    private static final int ACCENT = 0xFF4FC3F7;

    private float dp;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private volatile boolean busy = false;

    private TextView info, status, logView, logTitle;
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
        fwInstalled = readFwVersion();
        refreshInfo();
        status.setText(I18n.s("hint"));
        checkBtn.requestFocus();
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
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setPadding(px(56), px(32), px(56), px(40));
        col.setClipChildren(false);
        scroll.addView(col);

        TextView title = text(I18n.s("title"), 32, Color.WHITE, true);
        col.addView(title);

        info = text("", 17, 0xCCFFFFFF, false);
        info.setPadding(0, px(8), 0, px(18));
        col.addView(info);

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
        return scroll;
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

    /** Le version= de /system/etc/a95xz2-release; sem ficheiro: v4 se o modelo for A95X Z2. */
    private static int readFwVersion() {
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

    private String fwName(int v) { return v > 0 ? "v" + v : I18n.s("unknown"); }

    private PackageInfo pkgInfo(String pkg) {
        try {
            return getPackageManager().getPackageInfo(pkg, 0);
        } catch (PackageManager.NameNotFoundException e) {
            return null;
        }
    }

    @SuppressWarnings("deprecation")
    private String pkgVersion(String pkg) {
        PackageInfo pi = pkgInfo(pkg);
        return pi == null ? I18n.s("not_installed") : pi.versionName + " (" + pi.versionCode + ")";
    }

    private void refreshInfo() {
        info.setText(I18n.s("installed") + ":   " + I18n.s("firmware") + " " + fwName(fwInstalled)
                + "   ·   " + I18n.s("launcher") + " " + pkgVersion(LAUNCHER_PKG)
                + "   ·   " + I18n.s("updater") + " " + pkgVersion(getPackageName()));
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
                byte[] json;
                try {
                    json = Net.get(MANIFEST_URL, 1024 * 1024);
                } catch (Net.HttpError e) {
                    if (e.code == 404) { setStatus(I18n.s("no_info"), false); return; }
                    throw e;
                }
                byte[] sig;
                try {
                    sig = Net.get(SIG_URL, 16 * 1024);
                } catch (Net.HttpError e) {
                    if (e.code == 404) { setStatus(I18n.s("sig_error"), true); return; }
                    throw e;
                }
                byte[] pub;
                try (InputStream in = getResources().openRawResource(R.raw.ota_pub)) {
                    pub = Net.readAll(in);
                }
                if (!Net.verify(json, sig, pub)) { setStatus(I18n.s("sig_error"), true); return; }
                JSONObject m;
                try {
                    m = new JSONObject(new String(json, "UTF-8"));
                    if (m.optInt("schema", 0) != 1) throw new IllegalArgumentException("schema " + m.opt("schema"));
                } catch (Exception e) {
                    setStatus(I18n.f("bad_manifest", e.getMessage()), true);
                    return;
                }
                ui.post(() -> showManifest(m));
            } catch (Exception e) {
                setStatus(I18n.f("net_error", msg(e)), true);
            } finally {
                setBusy(false);
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
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.HORIZONTAL);
        box.setGravity(Gravity.CENTER_VERTICAL);
        box.setPadding(px(18), px(12), px(18), px(12));
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
        box.addView(txt, new LinearLayout.LayoutParams(0, -2, 1f));

        View btn = null;
        if (onInstall != null) {
            btn = button(I18n.s("install"), onInstall);
            LinearLayout.LayoutParams blp = new LinearLayout.LayoutParams(-2, -2);
            blp.setMargins(px(20), 0, px(6), 0);
            box.addView(btn, blp);
        }
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2);
        lp.setMargins(0, px(10), 0, 0);
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
