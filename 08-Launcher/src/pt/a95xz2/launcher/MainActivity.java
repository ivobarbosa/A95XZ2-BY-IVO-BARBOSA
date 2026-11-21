package pt.a95xz2.launcher;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.BroadcastReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.content.pm.ActivityInfo;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.graphics.Color;
import android.graphics.Rect;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.net.ConnectivityManager;
import android.net.NetworkCapabilities;
import android.net.Network;
import android.net.Uri;
import android.net.wifi.WifiManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.provider.Settings;
import android.text.InputFilter;
import android.text.InputType;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowManager;
import android.view.inputmethod.EditorInfo;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.HorizontalScrollView;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.FileReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.text.Collator;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Date;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * A95X Z2 Home: launcher leve para Android TV (sem AndroidX, sem rede, sem servicos).
 * Ecra: cabecalho (relogio, data, rede, temperatura, definicoes), fila de favoritos e
 * grelha com todas as apps. Comando: OK abre, MENU ou OK longo mostra as opcoes da app.
 */
public class MainActivity extends Activity {

    private static final String[] DEFAULT_FAVS = {
            "org.smarttube.stable", "com.google.android.youtube.tv", "com.netflix.ninja",
            "com.netflix.mediaclient", "com.spotify.tv.android", "com.spotify.music",
            "com.stremio.one", "com.android.vending", "com.android.chrome", "com.android.tv.settings"};
    private static final int COLS = 6;
    

    static final class App {
        String pkg;
        ComponentName cn;
        String label;
        ActivityInfo info;
    }

    private float dp;
    private PackageManager pm;
    private SharedPreferences prefs;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final HashMap<String, Drawable> art = new HashMap<>();   // cache de banner/icone por componente
    private final HashSet<String> hasBanner = new HashSet<>();

    // Onde esta um cartao (tag da fila): favoritos, recentes, categoria i ("c0", "c1"...) ou grelha.
    private static final String W_FAV = "fav", W_REC = "rec", W_GRID = "grid";
    private static final int MAX_RECENTS = 5;
    private static final int[] SAVER_OPTS = {0, 5, 10, 15, 30};   // minutos (0 = desligada)
    private static final int RC_EXPORT = 41, RC_IMPORT = 42;
    private static final String CFG_NAME = "a95xz2-home-config.json";

    /** Categoria do utilizador: nome + apps pela ordem escolhida. */
    static final class Cat {
        String name;
        final ArrayList<String> apps = new ArrayList<>();
    }

    private interface Pick { void done(ArrayList<String> sel); }

    private FrameLayout root;
    private ScrollView scroll;
    private LinearLayout col, favRow, grid, extraRows;
    private TextView favTitle, appsTitle, clock, date, net, temp, ram, emptyFav;
    private SignalView signal;
    private RamView ramIcon;

    private List<App> apps = new ArrayList<>();
    private final ArrayList<String> favs = new ArrayList<>();
    private final HashSet<String> hidden = new HashSet<>();
    private final ArrayList<String> recents = new ArrayList<>();
    private final ArrayList<Cat> cats = new ArrayList<>();
    private boolean showRecents = true;
    private boolean recentsDirty = false;
    private boolean showHidden = false;
    private String focusAfterBuild = null;   // pacote a focar depois de reconstruir
    private String focusWhere = W_GRID;
    private int loadGen = 0;
    private String movePkg = null;          // modo "mover": pacote a ser movido
    private String moveWhere = W_GRID;
    private String sortMode = "az";          // az | uso | pers
    private final ArrayList<String> appOrder = new ArrayList<>();   // ordem personalizada das apps
    private static final int MOVE_COLOR = 0xFF4FC3F7;

    // proteccao de ecra
    private FrameLayout saver;
    private LinearLayout saverBox;
    private TextView saverClock, saverDate;
    private int swallowKey = -1;            // tecla que tirou a proteccao: o seu UP tambem e engolido

    // ------------------------------------------------------------------ ciclo de vida

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        Window w = getWindow();
        w.addFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN);
        w.getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN | View.SYSTEM_UI_FLAG_FULLSCREEN);
        dp = getResources().getDisplayMetrics().density;
        pm = getPackageManager();
        prefs = getSharedPreferences("launcher", MODE_PRIVATE);
        loadPrefs();
        I18n.set(prefs.getString("lang", "auto"));
        setContentView(buildUi());
        registerReceivers();
        updateClock();
        updateStatus();
        reloadApps();
    }

    // RAM e temperatura a cada 5 s, so enquanto o launcher esta visivel.
    private final Runnable statusTick = new Runnable() {
        @Override public void run() { updateStatus(); ui.postDelayed(this, 5000); }
    };

    @Override
    protected void onResume() {
        super.onResume();
        updateClock();
        ui.removeCallbacks(statusTick);
        statusTick.run();
        if (recentsDirty && !apps.isEmpty()) { recentsDirty = false; rebuild(); }
        resetSaver();
        maybeAutostart();
    }

    @Override
    protected void onPause() {
        ui.removeCallbacks(statusTick);
        ui.removeCallbacks(saverRun);
        hideSaver(false);
        super.onPause();
    }

    @Override
    public void onWindowFocusChanged(boolean has) {
        super.onWindowFocusChanged(has);
        if (has) resetSaver();   // voltou de um dialogo: conta de novo
    }

    // ------------------------------------------------------------------ abrir ao ligar

    /**
     * Abre a app escolhida uma vez por arranque. Sem receiver BOOT_COMPLETED (o Android 10
     * bloqueia arranques de actividades em fundo): o HOME e a primeira actividade a aparecer,
     * por isso e aqui que se decide. O arranque fica marcado ANTES de abrir, para o HOME
     * seguinte nao voltar a abrir a app.
     */
    private void maybeAutostart() {
        String id = bootId();
        if (id.equals(prefs.getString("boot_seen", ""))) return;
        prefs.edit().putString("boot_seen", id).commit();
        final String pkg = prefs.getString("autostart", "");
        if (pkg.isEmpty() || SystemClock.elapsedRealtime() > 5 * 60 * 1000L) return;
        ui.postDelayed(() -> {
            Intent li = pm.getLeanbackLaunchIntentForPackage(pkg);
            if (li == null) li = pm.getLaunchIntentForPackage(pkg);
            if (li != null) startSafe(li);
        }, 1200);
    }

    private String bootId() {
        try (BufferedReader r = new BufferedReader(new FileReader("/proc/sys/kernel/random/boot_id"))) {
            String l = r.readLine();
            if (l != null && !l.trim().isEmpty()) return l.trim();
        } catch (Exception ignored) { }
        return "c" + Settings.Global.getInt(getContentResolver(), "boot_count", -1);
    }

    @Override
    public void onConfigurationChanged(android.content.res.Configuration c) {
        super.onConfigurationChanged(c);
        // idioma do sistema mudou e o launcher segue o sistema -> redesenhar com os novos textos
        if ("auto".equals(prefs.getString("lang", "auto"))) recreate();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        // Botao HOME com o launcher ja visivel: volta ao inicio.
        if (Intent.ACTION_MAIN.equals(intent.getAction())) { hideSaver(false); goTop(); }
    }

    @Override
    public void onBackPressed() {
        goTop();   // um launcher nunca fecha
    }

    @Override
    protected void onDestroy() {
        try { unregisterReceiver(tick); } catch (Exception ignored) { }
        try { unregisterReceiver(pkgs); } catch (Exception ignored) { }
        try { unregisterReceiver(netRx); } catch (Exception ignored) { }
        io.shutdownNow();
        super.onDestroy();
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_MENU || keyCode == KeyEvent.KEYCODE_INFO
                || keyCode == KeyEvent.KEYCODE_SETTINGS) {
            View f = getCurrentFocus();
            if (f != null && f.getTag() instanceof App) {
                showAppMenu((App) f.getTag(), whereOf(f));
            } else {
                showLauncherMenu();
            }
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    // ------------------------------------------------------------------ interface

    private int px(float v) { return Math.round(v * dp); }

    private View buildUi() {
        root = new FrameLayout(this);

        TextView mark = text("A95X Z2", 120, 0x0DFFFFFF, true);
        mark.setTypeface(Typeface.create("sans-serif-black", Typeface.NORMAL));
        FrameLayout.LayoutParams mlp = new FrameLayout.LayoutParams(-2, -2, Gravity.BOTTOM | Gravity.END);
        mlp.setMargins(0, 0, px(40), px(10));
        root.addView(mark, mlp);

        scroll = new ScrollView(this) {
            private View focusing;   // em requestChildFocus o findFocus() ainda devolve o anterior

            @Override
            public void requestChildFocus(View child, View focused) {
                focusing = focused;
                super.requestChildFocus(child, focused);
            }

            // Ao focar um cartao, mostra a fila inteira com o titulo (nao so o cartao).
            @Override
            protected int computeScrollDeltaToGetChildRectOnScreen(Rect r) {
                View f = focusing != null ? focusing : findFocus();
                if (f != null && f.getTag() instanceof App) {
                    int[] b = rowBounds(f);
                    if (b != null) {
                        r.top = Math.min(r.top, b[0]);
                        r.bottom = Math.max(r.bottom, b[1]);
                    }
                }
                return super.computeScrollDeltaToGetChildRectOnScreen(r);
            }
        };
        scroll.setVerticalScrollBarEnabled(false);
        scroll.setOverScrollMode(View.OVER_SCROLL_NEVER);
        scroll.setSmoothScrollingEnabled(true);
        scroll.setClipChildren(false);
        root.addView(scroll, new FrameLayout.LayoutParams(-1, -1));

        col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setPadding(px(56), px(32), px(56), px(48));
        col.setClipChildren(false);
        col.setClipToPadding(false);
        scroll.addView(col, new ScrollView.LayoutParams(-1, -2));

        col.addView(buildHeader());

        favTitle = sectionTitle(I18n.s("favorites"));
        col.addView(favTitle);
        favRow = hRow(W_FAV);
        HorizontalScrollView hs = hScroll(favRow);
        hs.setPadding(px(12), px(16), px(12), px(8));
        col.addView(hs, new LinearLayout.LayoutParams(-1, -2));
        emptyFav = text(I18n.s("empty_favs"), 15, 0x99FFFFFF, false);
        emptyFav.setVisibility(View.GONE);
        col.addView(emptyFav);

        // recentes + categorias do utilizador (refeitas em rebuild)
        extraRows = new LinearLayout(this);
        extraRows.setOrientation(LinearLayout.VERTICAL);
        extraRows.setClipChildren(false);
        extraRows.setClipToPadding(false);
        col.addView(extraRows, new LinearLayout.LayoutParams(-1, -2));

        appsTitle = sectionTitle(I18n.s("apps"));
        col.addView(appsTitle);
        grid = new LinearLayout(this);
        grid.setOrientation(LinearLayout.VERTICAL);
        grid.setClipChildren(false);
        grid.setClipToPadding(false);
        grid.setPadding(px(12), px(12), px(12), 0);
        col.addView(grid, new LinearLayout.LayoutParams(-1, -2));
        return root;
    }

    /** Fila horizontal de cartoes; a tag diz onde esta (W_FAV, W_REC, "c<i>"). */
    private LinearLayout hRow(String where) {
        LinearLayout r = new LinearLayout(this);
        r.setOrientation(LinearLayout.HORIZONTAL);
        r.setClipChildren(false);
        r.setClipToPadding(false);
        r.setTag(where);
        return r;
    }

    private HorizontalScrollView hScroll(LinearLayout row) {
        HorizontalScrollView hs = new HorizontalScrollView(this);
        hs.setHorizontalScrollBarEnabled(false);
        hs.setOverScrollMode(View.OVER_SCROLL_NEVER);
        hs.setClipChildren(false);
        hs.setClipToPadding(false);
        hs.addView(row);
        return hs;
    }

    /** Seccao com titulo + fila de cartoes pequenos (recentes e categorias). */
    private LinearLayout addSection(String title, String where) {
        LinearLayout sec = new LinearLayout(this);
        sec.setOrientation(LinearLayout.VERTICAL);
        sec.setClipChildren(false);
        sec.setClipToPadding(false);
        sec.addView(sectionTitle(title));
        LinearLayout row = hRow(where);
        HorizontalScrollView hs = hScroll(row);
        hs.setPadding(px(12), px(12), px(12), px(4));
        sec.addView(hs, new LinearLayout.LayoutParams(-1, -2));
        extraRows.addView(sec, new LinearLayout.LayoutParams(-1, -2));
        return row;
    }

    /** Onde esta o cartao: tag da fila que o contem. */
    private String whereOf(View card) {
        Object t = card.getParent() instanceof View ? ((View) card.getParent()).getTag() : null;
        return t instanceof String ? (String) t : W_GRID;
    }

    /** Topo de v em coordenadas do conteudo do ScrollView. */
    private int yIn(View v) {
        int y = 0;
        while (v != null && v != col) {
            y += v.getTop() - v.getScrollY();
            v = v.getParent() instanceof View ? (View) v.getParent() : null;
        }
        return y + col.getTop();
    }

    /** Limites verticais (titulo incluido) da fila do cartao focado; favoritos -> topo do ecra. */
    private int[] rowBounds(View card) {
        if (!(card.getParent() instanceof View)) return null;
        View row = (View) card.getParent();
        String w = whereOf(card);
        if (W_FAV.equals(w)) return new int[]{0, yIn(row) + row.getHeight()};
        if (W_GRID.equals(w)) {
            int top = grid.indexOfChild(row) == 0 ? yIn(appsTitle) : yIn(row);
            return new int[]{top, yIn(row) + row.getHeight() + px(16)};
        }
        // row -> HorizontalScrollView -> seccao
        View sec = row.getParent() instanceof View ? (View) ((View) row.getParent()).getParent() : null;
        if (sec == null) return null;
        int top = yIn(sec);
        return new int[]{top, top + sec.getHeight() + px(16)};   // folga: cartao focado cresce 8%
    }

    private View buildHeader() {
        LinearLayout h = new LinearLayout(this);
        h.setOrientation(LinearLayout.HORIZONTAL);
        h.setGravity(Gravity.CENTER_VERTICAL);

        LinearLayout left = new LinearLayout(this);
        left.setOrientation(LinearLayout.VERTICAL);
        clock = text("--:--", 54, Color.WHITE, false);
        clock.setTypeface(Typeface.create("sans-serif-light", Typeface.NORMAL));
        clock.setIncludeFontPadding(false);
        date = text("", 18, 0xB3FFFFFF, false);
        left.addView(clock);
        left.addView(date);
        h.addView(left, new LinearLayout.LayoutParams(0, -2, 1));

        signal = new SignalView(this);
        LinearLayout.LayoutParams slp = new LinearLayout.LayoutParams(px(22), px(18));
        slp.setMargins(0, 0, px(8), 0);
        h.addView(signal, slp);
        net = text("", 16, 0xCCFFFFFF, false);
        h.addView(net);
        ramIcon = new RamView(this);
        LinearLayout.LayoutParams rlp = new LinearLayout.LayoutParams(px(18), px(18));
        rlp.setMargins(px(26), 0, px(8), 0);
        h.addView(ramIcon, rlp);
        ram = text("", 16, 0xCCFFFFFF, false);
        h.addView(ram);
        temp = text("", 16, 0xCCFFFFFF, false);
        temp.setPadding(px(24), 0, px(24), 0);
        h.addView(temp);

        GearView gear = new GearView(this);
        gear.setOnClickListener(v -> showLauncherMenu());
        h.addView(gear, new LinearLayout.LayoutParams(px(42), px(42)));
        return h;
    }

    private TextView pill(String s) {
        TextView t = text(s, 16, Color.WHITE, false);
        t.setFocusable(true);
        t.setPadding(px(18), px(8), px(18), px(8));
        GradientDrawable g = new GradientDrawable();
        g.setCornerRadius(px(20));
        g.setColor(0x26FFFFFF);
        t.setBackground(g);
        t.setOnFocusChangeListener((v, f) -> {
            g.setColor(f ? 0xFFFFFFFF : 0x26FFFFFF);
            ((TextView) v).setTextColor(f ? 0xFF101826 : Color.WHITE);
        });
        return t;
    }

    /** Idioma do launcher: automatico (segue o sistema) ou um dos idiomas traduzidos. */
    private void pickLanguage() {
        final String cur = prefs.getString("lang", "auto");
        String[] items = new String[I18n.CODES.length + 2];
        items[0] = I18n.s("lang_auto");
        for (int i = 0; i < I18n.CODES.length; i++) items[i + 1] = I18n.NAMES[i];
        items[items.length - 1] = I18n.s("lang_system");
        int sel = "auto".equals(cur) ? 0 : I18n.indexOf(cur) + 1;
        new AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
                .setOnCancelListener(x -> backToGroup())
                .setTitle(I18n.s("language"))
                .setSingleChoiceItems(items, sel, (d, w) -> {
                    d.dismiss();
                    if (w == items.length - 1) {
                        startSafe(new Intent(Settings.ACTION_LOCALE_SETTINGS));
                        return;
                    }
                    String v = w == 0 ? "auto" : I18n.CODES[w - 1];
                    if (v.equals(cur)) return;
                    prefs.edit().putString("lang", v).apply();
                    I18n.set(v);
                    recreate();
                })
                .show();
    }

    /** Primeiro favorito que ainda esta instalado. */
    private String firstFav() {
        for (String p : favs) if (find(p) != null) return p;
        return favs.get(0);
    }

    private String sortLabel() {
        return I18n.s("sort_apps_prefix") + ("uso".equals(sortMode) ? I18n.s("most_used") : "pers".equals(sortMode) ? I18n.s("custom") : I18n.s("az"));
    }

    private TextView sectionTitle(String s) {
        TextView t = text(s, 20, 0xE6FFFFFF, true);
        t.setPadding(px(4), px(26), 0, px(2));
        return t;
    }

    private TextView text(String s, float sp, int color, boolean bold) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(sp);
        t.setTextColor(color);
        if (bold) t.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        return t;
    }

    /** Cartao 16:9 com banner (ou icone + nome) e o nome por baixo. */
    private View card(App a, boolean big, String where) {
        final boolean inFavs = W_FAV.equals(where);
        int w = px(big ? 236 : 170), h = px(big ? 133 : 96);
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setFocusable(true);
        box.setClipChildren(false);
        box.setTag(a);

        FrameLayout tile = new FrameLayout(this);
        GradientDrawable bg = new GradientDrawable();
        bg.setCornerRadius(px(10));
        bg.setColor(0xFF222B3B);
        tile.setBackground(bg);
        tile.setClipToOutline(true);

        ImageView img = new ImageView(this);
        tile.addView(img, new FrameLayout.LayoutParams(-1, -1));
        TextView inner = text(a.label, big ? 15 : 13, Color.WHITE, true);
        inner.setGravity(Gravity.CENTER);
        inner.setSingleLine(true);
        inner.setEllipsize(TextUtils.TruncateAt.END);
        FrameLayout.LayoutParams ilp = new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM);
        ilp.setMargins(px(8), 0, px(8), px(big ? 12 : 8));
        tile.addView(inner, ilp);
        // Contorno de foco POR FORA do cartao, encostado a ele (sem folga): a moldura tem a
        // largura exacta do traco, por isso nunca e cortado pelo recorte do cartao.
        int gap = px(3);
        FrameLayout frame = new FrameLayout(this);
        frame.setPadding(gap, gap, gap, gap);
        GradientDrawable ring = new GradientDrawable();
        ring.setCornerRadius(px(13));
        ring.setColor(Color.TRANSPARENT);
        frame.setBackground(ring);
        frame.addView(tile, new FrameLayout.LayoutParams(w, h));
        box.addView(frame, new LinearLayout.LayoutParams(w + 2 * gap, h + 2 * gap));

        TextView label = text(a.label, 13, 0x00FFFFFF, false);
        label.setSingleLine(true);
        label.setEllipsize(TextUtils.TruncateAt.END);
        label.setGravity(Gravity.CENTER_HORIZONTAL);
        label.setPadding(0, px(4), 0, 0);
        box.addView(label, new LinearLayout.LayoutParams(w + 2 * gap, -2));

        boolean isHidden = hidden.contains(a.pkg);
        if (isHidden) tile.setAlpha(0.45f);

        bindArt(a, img, inner, big, bg);

        box.setPivotX(w / 2f + gap);
        box.setPivotY(h / 2f + gap);
        box.setOnFocusChangeListener((v, f) -> {
            v.animate().scaleX(f ? 1.08f : 1f).scaleY(f ? 1.08f : 1f).setDuration(130).start();
            boolean mv = a.pkg.equals(movePkg) && where.equals(moveWhere);
            ring.setStroke(f ? px(mv ? 4 : 3) : 0, mv ? MOVE_COLOR : Color.WHITE);
            // nome por baixo em todos os cartoes focados (uniforme: banners e icones)
            label.setTextColor(f ? Color.WHITE : 0x00FFFFFF);
            if (f && inFavs) scroll.smoothScrollTo(0, 0);
        });
        box.setOnClickListener(v -> launch(a));
        box.setOnLongClickListener(v -> { showAppMenu(a, where); return true; });
        return box;
    }

    /** Cartao "+" no fim dos favoritos: escolher (marcar/desmarcar) as apps favoritas. */
    private View addCard() {
        int w = px(133), h = px(133), gap = px(3);
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setFocusable(true);
        box.setClipChildren(false);
        FrameLayout frame = new FrameLayout(this);
        frame.setPadding(gap, gap, gap, gap);
        GradientDrawable ring = new GradientDrawable();
        ring.setCornerRadius(px(13));
        ring.setColor(Color.TRANSPARENT);
        frame.setBackground(ring);
        TextView plus = text("+", 56, 0xCCFFFFFF, false);
        plus.setTypeface(Typeface.create("sans-serif-light", Typeface.NORMAL));
        plus.setGravity(Gravity.CENTER);
        GradientDrawable bg = new GradientDrawable();
        bg.setCornerRadius(px(10));
        bg.setColor(0x1AFFFFFF);
        bg.setStroke(px(2), 0x33FFFFFF, px(8), px(6));
        plus.setBackground(bg);
        frame.addView(plus, new FrameLayout.LayoutParams(w, h));
        box.addView(frame, new LinearLayout.LayoutParams(w + 2 * gap, h + 2 * gap));
        TextView label = text(I18n.s("edit_favs"), 13, 0x00FFFFFF, false);
        label.setGravity(Gravity.CENTER_HORIZONTAL);
        label.setSingleLine(true);
        label.setPadding(0, px(4), 0, 0);
        box.addView(label, new LinearLayout.LayoutParams(w + 2 * gap, -2));
        box.setPivotX(w / 2f + gap);
        box.setPivotY(h / 2f + gap);
        box.setOnFocusChangeListener((v, f) -> {
            v.animate().scaleX(f ? 1.08f : 1f).scaleY(f ? 1.08f : 1f).setDuration(130).start();
            ring.setStroke(f ? px(3) : 0, Color.WHITE);
            label.setTextColor(f ? Color.WHITE : 0x00FFFFFF);
            plus.setTextColor(f ? Color.WHITE : 0xCCFFFFFF);
            if (f) scroll.smoothScrollTo(0, 0);
        });
        box.setOnClickListener(v -> pickFavorites());
        return box;
    }

    /** Editar favoritos (usa o seleccionador generico). */
    private void pickFavorites() {
        pickApps(I18n.s("edit_favs"), I18n.s("edit_favs_hint"), favs, nf -> {
            favs.clear();
            favs.addAll(nf);
            savePrefs();
            focusAfterBuild = null;
            rebuild();
        });
    }

    /**
     * Seleccionador de apps: grelha de miniaturas em ecra inteiro; OK marca/desmarca (visto azul).
     * Guardar devolve as marcadas: as que ja estavam pela mesma ordem, as novas no fim.
     */
    private void pickApps(String titleText, String hintText, final List<String> current, final Pick cb) {
        final ArrayList<App> list = new ArrayList<>(apps);
        final boolean[] on = new boolean[list.size()];
        for (int i = 0; i < list.size(); i++) on[i] = current.contains(list.get(i).pkg);

        final android.app.Dialog d = new android.app.Dialog(this, android.R.style.Theme_Black_NoTitleBar_Fullscreen);
        FrameLayout pr = new FrameLayout(this);
        pr.setBackgroundColor(0xF20A0E16);
        LinearLayout pc = new LinearLayout(this);
        pc.setOrientation(LinearLayout.VERTICAL);
        pc.setPadding(px(56), px(32), px(56), px(24));
        pr.addView(pc, new FrameLayout.LayoutParams(-1, -1));

        TextView title = text(titleText, 26, Color.WHITE, true);
        title.setSingleLine(true);
        title.setEllipsize(TextUtils.TruncateAt.END);
        pc.addView(title);
        TextView hint = text(hintText, 14, 0x99FFFFFF, false);
        hint.setPadding(0, px(4), 0, px(14));
        pc.addView(hint);

        ScrollView sv = new ScrollView(this);
        sv.setVerticalScrollBarEnabled(false);
        sv.setClipChildren(false);
        LinearLayout g = new LinearLayout(this);
        g.setOrientation(LinearLayout.VERTICAL);
        g.setClipChildren(false);
        g.setClipToPadding(false);
        g.setPadding(px(12), px(10), px(12), px(10));
        sv.addView(g);
        pc.addView(sv, new LinearLayout.LayoutParams(-1, 0, 1));

        LinearLayout row = null;
        View first = null;
        for (int i = 0; i < list.size(); i++) {
            if (i % COLS == 0) {
                row = new LinearLayout(this);
                row.setOrientation(LinearLayout.HORIZONTAL);
                row.setClipChildren(false);
                row.setClipToPadding(false);
                row.setPadding(0, px(4), 0, px(4));
                g.addView(row, new LinearLayout.LayoutParams(-2, -2));
            }
            View c = pickTile(list.get(i), on, i);
            if (first == null) first = c;
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-2, -2);
            lp.setMargins(0, 0, px(6), px(2));
            row.addView(c, lp);
        }

        LinearLayout bar = new LinearLayout(this);
        bar.setGravity(Gravity.END);
        bar.setPadding(0, px(12), px(12), 0);
        TextView cancel = pill(I18n.s("cancel"));
        cancel.setOnClickListener(v -> d.dismiss());
        TextView save = pill(I18n.s("save"));
        save.setOnClickListener(v -> {
            // mantem a ordem dos que ja la estavam e junta os novos no fim
            ArrayList<String> nf = new ArrayList<>();
            for (String p : current)
                for (int i = 0; i < list.size(); i++)
                    if (list.get(i).pkg.equals(p) && on[i]) nf.add(p);
            for (int i = 0; i < list.size(); i++)
                if (on[i] && !nf.contains(list.get(i).pkg)) nf.add(list.get(i).pkg);
            d.dismiss();
            cb.done(nf);
        });
        LinearLayout.LayoutParams blp = new LinearLayout.LayoutParams(-2, -2);
        blp.setMargins(px(12), 0, 0, 0);
        bar.addView(cancel, blp);
        bar.addView(save, new LinearLayout.LayoutParams(blp));
        pc.addView(bar);

        d.setContentView(pr);
        d.show();
        if (first != null) first.requestFocus();
    }

    /** Miniatura do editor de favoritos: mesma arte da grelha + selo ✓ quando marcada. */
    private View pickTile(App a, boolean[] on, int idx) {
        int w = px(170), h = px(96), gap = px(3);
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setFocusable(true);
        box.setClipChildren(false);

        FrameLayout frame = new FrameLayout(this);
        frame.setPadding(gap, gap, gap, gap);
        GradientDrawable ring = new GradientDrawable();
        ring.setCornerRadius(px(13));
        ring.setColor(Color.TRANSPARENT);
        frame.setBackground(ring);

        FrameLayout tile = new FrameLayout(this);
        GradientDrawable bg = new GradientDrawable();
        bg.setCornerRadius(px(10));
        bg.setColor(0xFF222B3B);
        tile.setBackground(bg);
        tile.setClipToOutline(true);
        ImageView img = new ImageView(this);
        tile.addView(img, new FrameLayout.LayoutParams(-1, -1));
        TextView inner = text(a.label, 13, Color.WHITE, true);
        inner.setGravity(Gravity.CENTER);
        inner.setSingleLine(true);
        inner.setEllipsize(TextUtils.TruncateAt.END);
        FrameLayout.LayoutParams ilp = new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM);
        ilp.setMargins(px(8), 0, px(8), px(8));
        tile.addView(inner, ilp);
        bindArt(a, img, inner, false, bg);
        frame.addView(tile, new FrameLayout.LayoutParams(w, h));

        TextView badge = text("✓", 16, Color.WHITE, true);
        badge.setGravity(Gravity.CENTER);
        GradientDrawable bb = new GradientDrawable();
        bb.setShape(GradientDrawable.OVAL);
        bb.setColor(MOVE_COLOR);
        bb.setStroke(px(2), 0xFF0A0E16);
        badge.setBackground(bb);
        FrameLayout.LayoutParams bl = new FrameLayout.LayoutParams(px(28), px(28), Gravity.TOP | Gravity.END);
        bl.setMargins(0, px(8), px(8), 0);
        frame.addView(badge, bl);
        box.addView(frame, new LinearLayout.LayoutParams(w + 2 * gap, h + 2 * gap));

        TextView label = text(a.label, 13, 0xB3FFFFFF, false);
        label.setSingleLine(true);
        label.setEllipsize(TextUtils.TruncateAt.END);
        label.setGravity(Gravity.CENTER_HORIZONTAL);
        label.setPadding(0, px(4), 0, 0);
        box.addView(label, new LinearLayout.LayoutParams(w + 2 * gap, -2));

        Runnable paint = () -> {
            badge.setVisibility(on[idx] ? View.VISIBLE : View.GONE);
            tile.setAlpha(on[idx] ? 1f : 0.45f);
        };
        paint.run();
        box.setPivotX(w / 2f + gap);
        box.setPivotY(h / 2f + gap);
        box.setOnFocusChangeListener((v, f) -> {
            v.animate().scaleX(f ? 1.08f : 1f).scaleY(f ? 1.08f : 1f).setDuration(130).start();
            ring.setStroke(f ? px(3) : 0, Color.WHITE);
            label.setTextColor(f ? Color.WHITE : 0xB3FFFFFF);
        });
        box.setOnClickListener(v -> { on[idx] = !on[idx]; paint.run(); });
        return box;
    }

    /** Carrega banner/icone numa thread de fundo e guarda em cache. */
    private void bindArt(App a, ImageView img, TextView inner, boolean big, GradientDrawable bg) {
        String key = a.cn.flattenToShortString();
        Drawable d = art.get(key);
        if (d != null) { applyArt(a, img, inner, big, d, hasBanner.contains(key)); return; }
        img.setTag(key);
        io.execute(() -> {
            Drawable dd = null;
            boolean banner = false;
            try {
                dd = a.info.loadBanner(pm);
                banner = dd != null;
                if (dd == null) dd = a.info.loadIcon(pm);
            } catch (Exception ignored) { }
            final Drawable fd = dd;
            final boolean fb = banner;
            ui.post(() -> {
                if (fd == null) return;
                art.put(key, fd);
                if (fb) hasBanner.add(key);
                if (key.equals(img.getTag())) applyArt(a, img, inner, big, fd, fb);
            });
        });
    }

    private void applyArt(App a, ImageView img, TextView inner, boolean big, Drawable d, boolean banner) {
        // Cada ImageView precisa da sua propria instancia: o mesmo Drawable em dois cartoes
        // (favorito + grelha) partilha os limites e aparece com o tamanho do mais pequeno.
        Drawable.ConstantState cs = d.getConstantState();
        img.setImageDrawable(cs != null ? cs.newDrawable(getResources()).mutate() : d);
        if (banner) {
            img.setScaleType(ImageView.ScaleType.FIT_XY);
            img.setPadding(0, 0, 0, 0);
            inner.setVisibility(View.GONE);
        } else {
            // icone centrado; o nome aparece por baixo do cartao quando focado (igual aos banners)
            img.setScaleType(ImageView.ScaleType.FIT_CENTER);
            int p = px(big ? 28 : 20);
            img.setPadding(p, p, p, p);
            inner.setVisibility(View.GONE);
        }
    }

    // ------------------------------------------------------------------ apps

    private void reloadApps() {
        final int gen = ++loadGen;
        io.execute(() -> {
            LinkedHashMap<String, App> map = new LinkedHashMap<>();
            // Primeiro as actividades Leanback (versao TV), depois as normais.
            for (String cat : new String[]{Intent.CATEGORY_LEANBACK_LAUNCHER, Intent.CATEGORY_LAUNCHER}) {
                Intent i = new Intent(Intent.ACTION_MAIN).addCategory(cat);
                for (ResolveInfo ri : pm.queryIntentActivities(i, 0)) {
                    ActivityInfo ai = ri.activityInfo;
                    if (ai == null || getPackageName().equals(ai.packageName)) continue;
                    if (map.containsKey(ai.packageName)) continue;
                    App a = new App();
                    a.pkg = ai.packageName;
                    a.cn = new ComponentName(ai.packageName, ai.name);
                    a.info = ai;
                    CharSequence l = ri.loadLabel(pm);
                    a.label = l == null ? a.pkg : l.toString().trim();
                    map.put(a.pkg, a);
                }
            }
            final ArrayList<App> list = new ArrayList<>(map.values());
            final Collator c = Collator.getInstance(I18n.locale());
            Collections.sort(list, (x, y) -> c.compare(x.label, y.label));
            ui.post(() -> {
                if (gen != loadGen) return;
                apps = list;
                if (!prefs.getBoolean("init", false)) {
                    for (String p : DEFAULT_FAVS) if (map.containsKey(p) && !favs.contains(p)) favs.add(p);
                    prefs.edit().putBoolean("init", true).apply();
                    savePrefs();
                }
                rebuild();
            });
        });
    }

    private App find(String pkg) {
        for (App a : apps) if (a.pkg.equals(pkg)) return a;
        return null;
    }

    private void rebuild() {
        View cur = getCurrentFocus();
        String keepPkg = focusAfterBuild;
        String keepWhere = focusWhere;
        if (keepPkg == null && cur != null && cur.getTag() instanceof App) {
            keepPkg = ((App) cur.getTag()).pkg;
            keepWhere = whereOf(cur);
        }
        focusAfterBuild = null;

        favRow.removeAllViews();
        for (String p : favs) {
            App a = find(p);
            if (a == null) continue;
            View v = card(a, true, W_FAV);
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-2, -2);
            lp.setMargins(0, 0, px(12), 0);
            favRow.addView(v, lp);
        }
        favRow.addView(addCard(), new LinearLayout.LayoutParams(-2, -2));
        emptyFav.setVisibility(View.GONE);

        // recentes e categorias: so aparecem se tiverem pelo menos uma app instalada
        extraRows.removeAllViews();
        HashMap<String, LinearLayout> rows = new HashMap<>();
        rows.put(W_FAV, favRow);
        if (showRecents) {
            ArrayList<App> r = installed(recents);
            if (!r.isEmpty()) rows.put(W_REC, fillRow(addSection(I18n.s("recents"), W_REC), r, W_REC));
        }
        for (int c = 0; c < cats.size(); c++) {
            ArrayList<App> l = installed(cats.get(c).apps);
            if (!l.isEmpty()) rows.put("c" + c, fillRow(addSection(cats.get(c).name, "c" + c), l, "c" + c));
        }

        grid.removeAllViews();
        LinearLayout row = null;
        int i = 0;
        for (App a : gridApps()) {
            if (i % COLS == 0) {
                row = new LinearLayout(this);
                row.setOrientation(LinearLayout.HORIZONTAL);
                row.setClipChildren(false);
                row.setClipToPadding(false);
                row.setPadding(0, px(4), 0, px(4));
                row.setTag(W_GRID);
                grid.addView(row, new LinearLayout.LayoutParams(-2, -2));
            }
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-2, -2);
            lp.setMargins(0, 0, px(6), px(2));
            row.addView(card(a, false, W_GRID), lp);
            i++;
        }
        appsTitle.setText(showHidden ? I18n.s("apps_hidden_shown") : I18n.s("apps"));

        View target = null;
        if (keepPkg != null) {
            ViewGroup g = W_GRID.equals(keepWhere) ? grid : rows.get(keepWhere);
            if (g != null) target = findCard(g, keepPkg);
            if (target == null) target = findCard(col, keepPkg);
        }
        if (target == null) target = favRow.getChildCount() > 0 ? favRow.getChildAt(0) : firstGridCard();
        // em modo mover o cartao tem de ficar focado mesmo que se tenha usado rato/toque
        if (target != null) { if (movePkg != null) target.requestFocusFromTouch(); else target.requestFocus(); }
    }

    /** Pacotes -> apps instaladas (as desinstaladas sao ignoradas, sem as apagar da lista). */
    private ArrayList<App> installed(List<String> pkgs) {
        ArrayList<App> l = new ArrayList<>();
        for (String p : pkgs) {
            App a = find(p);
            if (a != null) l.add(a);
        }
        return l;
    }

    private LinearLayout fillRow(LinearLayout row, List<App> l, String where) {
        for (App a : l) {
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-2, -2);
            lp.setMargins(0, 0, px(6), 0);
            row.addView(card(a, false, where), lp);
        }
        return row;
    }

    /** Apps da grelha, ja filtradas (ocultas) e ordenadas conforme o modo escolhido. */
    private ArrayList<App> gridApps() {
        ArrayList<App> l = new ArrayList<>();
        for (App a : apps) if (showHidden || !hidden.contains(a.pkg)) l.add(a);   // apps ja vem A-Z
        if ("uso".equals(sortMode)) {
            Collections.sort(l, (x, y) -> Integer.compare(prefs.getInt("n_" + y.pkg, 0), prefs.getInt("n_" + x.pkg, 0)));
        } else if ("pers".equals(sortMode)) {
            Collections.sort(l, (x, y) -> {
                int ix = appOrder.indexOf(x.pkg), iy = appOrder.indexOf(y.pkg);
                if (ix < 0) ix = Integer.MAX_VALUE;
                if (iy < 0) iy = Integer.MAX_VALUE;
                return Integer.compare(ix, iy);   // sort estavel: as novas ficam no fim por ordem A-Z
            });
        }
        return l;
    }

    // ------------------------------------------------------------------ modo mover

    /** where: W_FAV, W_GRID ou "c<i>" (categoria). Os recentes nao se movem. */
    private void startMove(String pkg, String where) {
        if (W_GRID.equals(where) && !"pers".equals(sortMode)) {
            appOrder.clear();
            for (App a : gridApps()) appOrder.add(a.pkg);
            sortMode = "pers";
            savePrefs();
        }
        movePkg = pkg;
        moveWhere = where;
        focusAfterBuild = pkg;
        focusWhere = where;
        rebuild();
        Toast.makeText(this, I18n.s("move_hint"), Toast.LENGTH_SHORT).show();
    }

    /** Lista que o modo mover altera (favoritos ou apps de uma categoria); null na grelha. */
    private ArrayList<String> moveList(String where) {
        if (W_FAV.equals(where)) return favs;
        Cat c = catOf(where);
        return c == null ? null : c.apps;
    }

    private Cat catOf(String where) {
        if (where == null || !where.startsWith("c")) return null;
        try {
            int i = Integer.parseInt(where.substring(1));
            return i >= 0 && i < cats.size() ? cats.get(i) : null;
        } catch (NumberFormatException e) { return null; }
    }

    private void moveStep(int d) {
        ArrayList<String> l;
        ArrayList<String> target = moveList(moveWhere);
        if (target == null) {
            for (App a : gridApps()) if (!appOrder.contains(a.pkg)) appOrder.add(a.pkg);
            target = appOrder;
            l = new ArrayList<>();
            for (App a : gridApps()) l.add(a.pkg);    // so as visiveis, pela ordem actual
        } else {
            l = new ArrayList<>();
            for (App a : installed(target)) l.add(a.pkg);   // so as instaladas (as que se veem)
        }
        int i = l.indexOf(movePkg), j = i + d;
        if (i < 0 || j < 0 || j >= l.size()) return;
        l.remove(i);
        l.add(j, movePkg);
        // reconstroi a lista completa: visiveis pela nova ordem, as restantes no fim
        ArrayList<String> full = new ArrayList<>(l);
        for (String p : target) if (!full.contains(p)) full.add(p);
        target.clear();
        target.addAll(full);
        savePrefs();
        focusAfterBuild = movePkg;
        focusWhere = moveWhere;
        rebuild();
    }

    private void endMove() {
        String p = movePkg;
        movePkg = null;
        savePrefs();
        focusAfterBuild = p;
        focusWhere = moveWhere;
        rebuild();
    }

    @Override
    public boolean dispatchKeyEvent(KeyEvent e) {
        int k = e.getKeyCode();
        boolean down = e.getAction() == KeyEvent.ACTION_DOWN;
        resetSaver();
        // proteccao de ecra visivel: qualquer tecla so a tira (e o resto dessa tecla e ignorado)
        if (saver != null && saver.getVisibility() == View.VISIBLE) {
            if (down) { swallowKey = k; hideSaver(true); }
            return true;
        }
        if (k == swallowKey) {
            if (e.getAction() == KeyEvent.ACTION_UP) swallowKey = -1;
            return true;
        }
        if (movePkg == null) return super.dispatchKeyEvent(e);
        boolean inGrid = W_GRID.equals(moveWhere);
        switch (k) {
            case KeyEvent.KEYCODE_DPAD_LEFT: if (down) moveStep(-1); return true;
            case KeyEvent.KEYCODE_DPAD_RIGHT: if (down) moveStep(+1); return true;
            case KeyEvent.KEYCODE_DPAD_UP: if (down && inGrid) moveStep(-COLS); return true;
            case KeyEvent.KEYCODE_DPAD_DOWN: if (down && inGrid) moveStep(+COLS); return true;
            case KeyEvent.KEYCODE_DPAD_CENTER: case KeyEvent.KEYCODE_ENTER: case KeyEvent.KEYCODE_BACK:
            case KeyEvent.KEYCODE_MENU:
                if (!down) endMove();
                return true;
            default: return super.dispatchKeyEvent(e);
        }
    }

    // ------------------------------------------------------------------ escolhas (ocultar, ordenar)

    private void pickVisible() {
        final ArrayList<App> list = new ArrayList<>(apps);
        final String[] names = new String[list.size()];
        final boolean[] on = new boolean[list.size()];
        for (int i = 0; i < list.size(); i++) {
            names[i] = list.get(i).label;
            on[i] = !hidden.contains(list.get(i).pkg);
        }
        new AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
                .setOnCancelListener(x -> backToGroup())
                .setTitle(I18n.s("visible_apps"))
                .setMultiChoiceItems(names, on, (d, i, c) -> on[i] = c)
                .setPositiveButton(I18n.s("save"), (d, w) -> {
                    hidden.clear();
                    for (int i = 0; i < list.size(); i++) if (!on[i]) hidden.add(list.get(i).pkg);
                    savePrefs();
                    rebuild();
                })
                .setNegativeButton(I18n.s("cancel"), null)
                .show();
    }

    /** Ordenar favoritos: A-Z ou mais usadas (aplica uma vez) ou manual (modo mover). */
    private void pickFavSort(String fromPkg) {
        String[] names = {I18n.s("alpha"), I18n.s("by_use"), I18n.s("manual")};
        new AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
                .setOnCancelListener(x -> backToGroup())
                .setTitle(I18n.s("sort_favs"))
                .setItems(names, (d, w) -> {
                    if (w == 2) { startMove(fromPkg, W_FAV); return; }
                    final Collator c = Collator.getInstance(I18n.locale());
                    Collections.sort(favs, (x, y) -> {
                        if (w == 1) {
                            int r = Integer.compare(prefs.getInt("n_" + y, 0), prefs.getInt("n_" + x, 0));
                            if (r != 0) return r;
                        }
                        App ax = find(x), ay = find(y);
                        return c.compare(ax == null ? x : ax.label, ay == null ? y : ay.label);
                    });
                    savePrefs();
                    focusAfterBuild = fromPkg;
                    focusWhere = W_FAV;
                    rebuild();
                })
                .show();
    }

    private void pickSort() {
        final String[] modes = {"az", "uso", "pers"};
        String[] names = {I18n.s("alpha"), I18n.s("by_use"), I18n.s("custom_long")};
        int cur = Arrays.asList(modes).indexOf(sortMode);
        new AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
                .setOnCancelListener(x -> backToGroup())
                .setTitle(I18n.s("sort_apps"))
                .setSingleChoiceItems(names, cur, (d, w) -> {
                    d.dismiss();
                    if ("pers".equals(modes[w])) {
                        ArrayList<App> g = gridApps();
                        if (!"pers".equals(sortMode)) {
                            appOrder.clear();
                            for (App a : g) appOrder.add(a.pkg);
                        }
                        sortMode = "pers";
                        savePrefs();
                        if (!g.isEmpty()) startMove(gridApps().get(0).pkg, W_GRID);
                    } else {
                        sortMode = modes[w];
                        savePrefs();
                        rebuild();
                    }
                })
                .show();
    }

    private View firstGridCard() {
        if (grid.getChildCount() == 0) return null;
        ViewGroup r = (ViewGroup) grid.getChildAt(0);
        return r.getChildCount() > 0 ? r.getChildAt(0) : null;
    }

    private View findCard(ViewGroup g, String pkg) {
        for (int i = 0; i < g.getChildCount(); i++) {
            View v = g.getChildAt(i);
            if (v.getTag() instanceof App && ((App) v.getTag()).pkg.equals(pkg)) return v;
            if (v instanceof ViewGroup && !(v.getTag() instanceof App)) {
                View r = findCard((ViewGroup) v, pkg);
                if (r != null) return r;
            }
        }
        return null;
    }

    private void goTop() {
        scroll.smoothScrollTo(0, 0);
        View t = favRow.getChildCount() > 0 ? favRow.getChildAt(0) : firstGridCard();
        if (t != null) t.requestFocus();
    }

    private void launch(App a) {
        prefs.edit().putInt("n_" + a.pkg, prefs.getInt("n_" + a.pkg, 0) + 1).apply();
        addRecent(a.pkg);
        try {
            Intent i = new Intent(Intent.ACTION_MAIN);
            i.setComponent(a.cn);
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED);
            startActivity(i);
        } catch (Exception e) {
            Intent li = pm.getLeanbackLaunchIntentForPackage(a.pkg);
            if (li == null) li = pm.getLaunchIntentForPackage(a.pkg);
            if (li != null) startActivity(li.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        }
    }

    // ------------------------------------------------------------------ recentes

    /** Guarda a app no topo dos recentes (sem repetidas, maximo 5). A fila e refeita no onResume. */
    private void addRecent(String pkg) {
        recents.remove(pkg);
        recents.add(0, pkg);
        while (recents.size() > MAX_RECENTS) recents.remove(recents.size() - 1);
        prefs.edit().putString("recents", TextUtils.join(",", recents)).apply();
        recentsDirty = true;
    }

    private void clearRecents() {
        recents.clear();
        prefs.edit().putString("recents", "").apply();
        rebuild();
        toast(I18n.s("recents_cleared"));
    }

    // ------------------------------------------------------------------ menus

    private void showAppMenu(App a, String where) {
        lastGroup = null;
        final boolean inFavs = W_FAV.equals(where);
        final boolean inRec = W_REC.equals(where);
        final Cat inCat = catOf(where);
        final boolean fav = favs.contains(a.pkg);
        final boolean hid = hidden.contains(a.pkg);
        ArrayList<String> opts = new ArrayList<>();
        ArrayList<Runnable> acts = new ArrayList<>();
        opts.add(I18n.s("open")); acts.add(() -> launch(a));
        if (!inRec) { opts.add(I18n.s("move")); acts.add(() -> startMove(a.pkg, where)); }
        if (inFavs) { opts.add(I18n.s("sort_favs_more")); acts.add(() -> pickFavSort(a.pkg)); }
        else if (W_GRID.equals(where)) { opts.add(I18n.s("sort_apps_more")); acts.add(this::pickSort); }
        if (fav) {
            opts.add(I18n.s("remove_fav"));
            acts.add(() -> { favs.remove(a.pkg); savePrefs(); focusAfterBuild = a.pkg; focusWhere = inFavs ? W_GRID : where; rebuild(); });
        } else {
            opts.add(I18n.s("add_fav"));
            acts.add(() -> { favs.add(a.pkg); hidden.remove(a.pkg); savePrefs(); focusAfterBuild = a.pkg; focusWhere = W_FAV; rebuild(); });
        }
        if (inCat != null) {
            opts.add(I18n.s("remove_from_cat").replace("%s", inCat.name));
            acts.add(() -> { inCat.apps.remove(a.pkg); savePrefs(); focusAfterBuild = a.pkg; focusWhere = W_GRID; rebuild(); });
        }
        opts.add(I18n.s("add_to_cat")); acts.add(() -> pickCatFor(a));
        if (inRec) {
            opts.add(I18n.s("remove_from_recents"));
            acts.add(() -> {
                recents.remove(a.pkg);
                prefs.edit().putString("recents", TextUtils.join(",", recents)).apply();
                rebuild();
            });
        }
        if (W_GRID.equals(where)) {
            opts.add(hid ? I18n.s("show_in_list") : I18n.s("hide_from_list"));
            acts.add(() -> {
                if (hid) hidden.remove(a.pkg); else hidden.add(a.pkg);
                savePrefs(); rebuild();
            });
        }
        opts.add(I18n.s("app_info"));
        acts.add(() -> startSafe(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                Uri.fromParts("package", a.pkg, null))));
        opts.add(I18n.s("uninstall"));
        acts.add(() -> startSafe(new Intent(Intent.ACTION_DELETE, Uri.fromParts("package", a.pkg, null))));
        menu(a.label, opts, acts);
    }

    /** Menu da roda dentada (1.3): 5 grupos curtos em vez de uma lista comprida. */
    /** Grupo do menu de onde se abriu o dialogo atual: VOLTAR regressa la (null = nao veio do menu). */
    private Runnable lastGroup;

    private void backToGroup() {
        Runnable g = lastGroup;
        if (g != null) g.run();
    }

    private void showLauncherMenu() {
        lastGroup = null;
        ArrayList<String> opts = new ArrayList<>();
        ArrayList<Runnable> acts = new ArrayList<>();
        opts.add(I18n.s("grp_favs") + "  ›"); acts.add(this::menuFavorites);
        opts.add(I18n.s("grp_apps") + "  ›"); acts.add(this::menuApps);
        opts.add(I18n.s("grp_custom") + "  ›"); acts.add(this::showLauncherOptions);
        opts.add(I18n.s("grp_system") + "  ›"); acts.add(this::menuSystem);
        opts.add(I18n.s("about")); acts.add(this::showAbout);
        menu("A95X Z2 Home", opts, acts);
    }

    private void menuFavorites() {
        lastGroup = this::menuFavorites;
        ArrayList<String> opts = new ArrayList<>();
        ArrayList<Runnable> acts = new ArrayList<>();
        opts.add(I18n.s("edit_favs")); acts.add(this::pickFavorites);
        opts.add(I18n.s("sort_favs")); acts.add(() -> { if (!favs.isEmpty()) pickFavSort(firstFav()); });
        menu(I18n.s("grp_favs"), opts, acts, this::showLauncherMenu);
    }

    private void menuApps() {
        lastGroup = this::menuApps;
        ArrayList<String> opts = new ArrayList<>();
        ArrayList<Runnable> acts = new ArrayList<>();
        opts.add(I18n.s("categories")); acts.add(this::showCategories);
        opts.add(I18n.s("show_hide_apps")); acts.add(this::pickVisible);
        opts.add(sortLabel()); acts.add(this::pickSort);
        menu(I18n.s("grp_apps"), opts, acts, this::showLauncherMenu);
    }

    private void menuSystem() {
        lastGroup = this::menuSystem;
        ArrayList<String> opts = new ArrayList<>();
        ArrayList<Runnable> acts = new ArrayList<>();
        // A95X Z2 Updater (escondido da lista de apps): mesma entrada que Definicoes -> Atualizacao do sistema
        Intent up = new Intent("android.settings.SYSTEM_UPDATE_SETTINGS");
        if (pm.resolveActivity(up, 0) != null) { opts.add(I18n.s("system_update")); acts.add(() -> startSafe(up)); }
        opts.add(I18n.s("network")); acts.add(() -> startSafe(new Intent(Settings.ACTION_WIFI_SETTINGS)));
        opts.add(I18n.s("android_settings"));
        acts.add(() -> {
            Intent i = pm.getLaunchIntentForPackage("com.android.tv.settings");
            startSafe(i != null ? i : new Intent(Settings.ACTION_SETTINGS));
        });
        // Magisk 31.1 ja nao mostra aviso de pedido de root: o acesso da-se no separador Superuser ("+")
        Intent mg = pm.getLaunchIntentForPackage("com.topjohnwu.magisk");
        if (mg != null) { opts.add(I18n.s("root_apps")); acts.add(() -> startSafe(mg)); }
        menu(I18n.s("grp_system"), opts, acts, this::showLauncherMenu);
    }

    /** Submenu: recentes, abrir ao ligar, proteccao de ecra, exportar/importar. */
    private void showLauncherOptions() {
        lastGroup = this::showLauncherOptions;
        ArrayList<String> opts = new ArrayList<>();
        ArrayList<Runnable> acts = new ArrayList<>();
        opts.add(I18n.s("show_recents") + ": " + I18n.s(showRecents ? "yes" : "no"));
        acts.add(() -> {
            showRecents = !showRecents;
            prefs.edit().putBoolean("show_recents", showRecents).apply();
            rebuild();
        });
        opts.add(I18n.s("clear_recents")); acts.add(this::clearRecents);
        App as = find(prefs.getString("autostart", ""));
        opts.add(I18n.s("autostart") + ": " + (as == null ? I18n.s("none") : as.label));
        acts.add(this::pickAutostart);
        opts.add(I18n.s("screensaver") + ": " + saverLabel(saverMinutes()));
        acts.add(this::pickSaver);
        opts.add(I18n.s("language")); acts.add(this::pickLanguage);
        opts.add(I18n.s("export_cfg")); acts.add(this::exportConfig);
        opts.add(I18n.s("import_cfg")); acts.add(this::importConfig);
        menu(I18n.s("grp_custom"), opts, acts, this::showLauncherMenu);
    }

    private void pickAutostart() {
        final ArrayList<App> list = new ArrayList<>(apps);
        String cur = prefs.getString("autostart", "");
        String[] names = new String[list.size() + 1];
        names[0] = I18n.s("none");
        int sel = cur.isEmpty() ? 0 : -1;
        for (int i = 0; i < list.size(); i++) {
            names[i + 1] = list.get(i).label;
            if (list.get(i).pkg.equals(cur)) sel = i + 1;
        }
        new AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
                .setOnCancelListener(x -> backToGroup())
                .setTitle(I18n.s("autostart"))
                .setSingleChoiceItems(names, sel, (d, w) -> {
                    d.dismiss();
                    prefs.edit().putString("autostart", w == 0 ? "" : list.get(w - 1).pkg).apply();
                })
                .show();
    }

    private int saverMinutes() { return prefs.getInt("saver_min", 10); }

    private String saverLabel(int m) {
        return m <= 0 ? I18n.s("off") : I18n.s("minutes").replace("%d", String.valueOf(m));
    }

    private void pickSaver() {
        String[] names = new String[SAVER_OPTS.length];
        int sel = 0;
        for (int i = 0; i < SAVER_OPTS.length; i++) {
            names[i] = saverLabel(SAVER_OPTS[i]);
            if (SAVER_OPTS[i] == saverMinutes()) sel = i;
        }
        new AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
                .setOnCancelListener(x -> backToGroup())
                .setTitle(I18n.s("screensaver"))
                .setSingleChoiceItems(names, sel, (d, w) -> {
                    d.dismiss();
                    prefs.edit().putInt("saver_min", SAVER_OPTS[w]).apply();
                    resetSaver();
                })
                .show();
    }

    // ------------------------------------------------------------------ categorias

    private void showCategories() {
        ArrayList<String> opts = new ArrayList<>();
        ArrayList<Runnable> acts = new ArrayList<>();
        opts.add(I18n.s("new_category"));
        acts.add(() -> askName(I18n.s("new_category"), "", n -> {
            Cat c = new Cat();
            c.name = n;
            cats.add(c);
            savePrefs();
            editCatApps(c);
        }));
        for (final Cat c : cats) {
            opts.add(c.name + "  (" + installed(c.apps).size() + ")");
            acts.add(() -> showCatMenu(c));
        }
        menu(I18n.s("categories"), opts, acts, this::backToGroup);
    }

    private void showCatMenu(final Cat c) {
        ArrayList<String> opts = new ArrayList<>();
        ArrayList<Runnable> acts = new ArrayList<>();
        opts.add(I18n.s("edit_apps")); acts.add(() -> editCatApps(c));
        opts.add(I18n.s("rename"));
        acts.add(() -> askName(I18n.s("rename"), c.name, n -> { c.name = n; savePrefs(); rebuild(); showCategories(); }));
        int i = cats.indexOf(c);
        if (i > 0) { opts.add(I18n.s("move_up")); acts.add(() -> moveCat(c, -1)); }
        if (i < cats.size() - 1) { opts.add(I18n.s("move_down")); acts.add(() -> moveCat(c, +1)); }
        opts.add(I18n.s("delete"));
        acts.add(() -> new AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
                .setTitle(I18n.s("delete"))
                .setMessage(I18n.s("delete_cat_q").replace("%s", c.name))
                .setPositiveButton(I18n.s("delete"), (d, w) -> { cats.remove(c); savePrefs(); rebuild(); })
                .setNegativeButton(I18n.s("cancel"), null)
                .show());
        menu(c.name, opts, acts);
    }

    private void moveCat(Cat c, int d) {
        int i = cats.indexOf(c), j = i + d;
        if (i < 0 || j < 0 || j >= cats.size()) return;
        cats.remove(i);
        cats.add(j, c);
        savePrefs();
        rebuild();
        showCategories();
    }

    private void editCatApps(final Cat c) {
        pickApps(I18n.s("edit_apps") + " \u00b7 " + c.name, I18n.s("pick_hint"), c.apps, sel -> {
            c.apps.clear();
            c.apps.addAll(sel);
            savePrefs();
            rebuild();
        });
    }

    /** "Juntar a uma categoria": lista as categorias (+ nova). */
    private void pickCatFor(final App a) {
        ArrayList<String> opts = new ArrayList<>();
        ArrayList<Runnable> acts = new ArrayList<>();
        for (final Cat c : cats) {
            if (c.apps.contains(a.pkg)) continue;
            opts.add(c.name);
            acts.add(() -> { c.apps.add(a.pkg); savePrefs(); rebuild(); });
        }
        opts.add(I18n.s("new_category"));
        acts.add(() -> askName(I18n.s("new_category"), "", n -> {
            Cat c = new Cat();
            c.name = n;
            c.apps.add(a.pkg);
            cats.add(c);
            savePrefs();
            rebuild();
        }));
        menu(I18n.s("add_to_cat"), opts, acts);
    }

    private interface Named { void done(String name); }

    /** Pede um nome (teclado no ecra). Nome vazio e ignorado. */
    private void askName(String title, String cur, final Named cb) {
        final EditText e = new EditText(this);
        e.setSingleLine(true);
        e.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);
        e.setImeOptions(EditorInfo.IME_ACTION_DONE);
        e.setFilters(new InputFilter[]{new InputFilter.LengthFilter(32)});
        e.setHint(I18n.s("category_name"));
        e.setText(cur);
        e.setSelection(cur.length());
        FrameLayout wrap = new FrameLayout(this);
        wrap.setPadding(px(24), px(8), px(24), 0);
        wrap.addView(e);
        final AlertDialog d = new AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
                .setTitle(title)
                .setView(wrap)
                .setPositiveButton(I18n.s("save"), (dd, w) -> {
                    String n = e.getText().toString().trim();
                    if (!n.isEmpty()) cb.done(n);
                })
                .setNegativeButton(I18n.s("cancel"), null)
                .create();
        e.setOnEditorActionListener((v, id, ev) -> {
            if (id == EditorInfo.IME_ACTION_DONE) {
                d.getButton(AlertDialog.BUTTON_POSITIVE).performClick();
                return true;
            }
            return false;
        });
        d.show();
        e.requestFocus();
    }

    // ------------------------------------------------------------------ exportar / importar

    private File cfgFile() {
        File dir = getExternalFilesDir(null);
        return dir == null ? null : new File(dir, CFG_NAME);
    }

    private void exportConfig() {
        Intent i = new Intent(Intent.ACTION_CREATE_DOCUMENT)
                .addCategory(Intent.CATEGORY_OPENABLE)
                .setType("application/json")
                .putExtra(Intent.EXTRA_TITLE, CFG_NAME);
        try {
            if (i.resolveActivity(pm) == null) throw new IllegalStateException();
            startActivityForResult(i, RC_EXPORT);
        } catch (Exception e) {
            // sem SAF: ficheiro na pasta da app no armazenamento externo
            File f = cfgFile();
            try (OutputStream os = new FileOutputStream(f)) {
                writeConfig(os);
                toast(I18n.s("saved_to") + f.getAbsolutePath());
            } catch (Exception ex) {
                toast(I18n.s("cfg_error"));
            }
        }
    }

    private void importConfig() {
        Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT)
                .addCategory(Intent.CATEGORY_OPENABLE)
                .setType("application/json");
        try {
            if (i.resolveActivity(pm) == null) throw new IllegalStateException();
            startActivityForResult(i, RC_IMPORT);
        } catch (Exception e) {
            File f = cfgFile();
            try (InputStream is = new FileInputStream(f)) {
                applyConfig(readAll(is));
                toast(I18n.s("import_ok") + " (" + f.getAbsolutePath() + ")");
                recreate();
            } catch (Exception ex) {
                toast(I18n.s("cfg_error") + (f == null ? "" : " (" + f.getAbsolutePath() + ")"));
            }
        }
    }

    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        super.onActivityResult(req, res, data);
        if (req != RC_EXPORT && req != RC_IMPORT) return;
        if (res != RESULT_OK || data == null || data.getData() == null) return;
        Uri u = data.getData();
        if (req == RC_EXPORT) {
            OutputStream os = null;
            try {
                try { os = getContentResolver().openOutputStream(u, "wt"); }
                catch (Exception e) { os = getContentResolver().openOutputStream(u, "w"); }
                writeConfig(os);
                toast(I18n.s("export_ok"));
            } catch (Exception e) {
                toast(I18n.s("cfg_error"));
            } finally {
                try { if (os != null) os.close(); } catch (Exception ignored) { }
            }
        } else {
            try (InputStream is = getContentResolver().openInputStream(u)) {
                applyConfig(readAll(is));
                toast(I18n.s("import_ok"));
                recreate();
            } catch (Exception e) {
                toast(I18n.s("cfg_error"));
            }
        }
    }

    private static String readAll(InputStream is) throws Exception {
        StringBuilder sb = new StringBuilder();
        try (BufferedReader r = new BufferedReader(new InputStreamReader(is, "UTF-8"))) {
            char[] buf = new char[4096];
            int n;
            while ((n = r.read(buf)) > 0) {
                sb.append(buf, 0, n);
                if (sb.length() > 256 * 1024) throw new IllegalArgumentException("grande demais");
            }
        }
        return sb.toString();
    }

    /** So a configuracao do launcher: nada de contagens de uso, recentes nem dados do sistema. */
    private void writeConfig(OutputStream os) throws Exception {
        JSONObject o = new JSONObject();
        o.put("app", getPackageName());
        o.put("version", 1);
        o.put("favs", new JSONArray(favs));
        o.put("hidden", new JSONArray(new ArrayList<>(hidden)));
        o.put("order", new JSONArray(appOrder));
        o.put("sort", sortMode);
        o.put("lang", prefs.getString("lang", "auto"));
        o.put("categories", catsJson());
        o.put("show_recents", showRecents);
        o.put("autostart", prefs.getString("autostart", ""));
        o.put("screensaver", saverMinutes());
        os.write(o.toString(2).getBytes("UTF-8"));
        os.flush();
    }

    /** Valida tudo primeiro; so depois aplica (ficheiro invalido nao altera nada). */
    private void applyConfig(String json) throws Exception {
        JSONObject o = new JSONObject(json);
        if (o.optInt("version", -1) != 1) throw new IllegalArgumentException("versao");
        ArrayList<String> nf = pkgList(o.optJSONArray("favs"));
        ArrayList<String> nh = pkgList(o.optJSONArray("hidden"));
        ArrayList<String> no = pkgList(o.optJSONArray("order"));
        String sort = o.optString("sort", "az");
        if (!Arrays.asList("az", "uso", "pers").contains(sort)) throw new IllegalArgumentException("sort");
        String lang = o.optString("lang", "auto");
        if (!"auto".equals(lang) && I18n.indexOf(lang) < 0) throw new IllegalArgumentException("lang");
        ArrayList<Cat> nc = parseCats(o.optJSONArray("categories"));
        boolean rec = o.optBoolean("show_recents", true);
        String auto = o.optString("autostart", "");
        if (!auto.isEmpty() && !isPkg(auto)) throw new IllegalArgumentException("autostart");
        int sv = o.optInt("screensaver", 10);
        boolean okSv = false;
        for (int m : SAVER_OPTS) if (m == sv) okSv = true;
        if (!okSv) throw new IllegalArgumentException("screensaver");

        favs.clear(); favs.addAll(nf);
        hidden.clear(); hidden.addAll(nh);
        appOrder.clear(); appOrder.addAll(no);
        sortMode = sort;
        cats.clear(); cats.addAll(nc);
        showRecents = rec;
        savePrefs();
        prefs.edit().putString("lang", lang).putBoolean("show_recents", rec)
                .putString("autostart", auto).putInt("saver_min", sv).putBoolean("init", true).commit();
        I18n.set(lang);
    }

    private static boolean isPkg(String s) {
        return s != null && s.length() < 256 && s.matches("[A-Za-z0-9_]+(\\.[A-Za-z0-9_]+)+");
    }

    private static ArrayList<String> pkgList(JSONArray a) throws Exception {
        ArrayList<String> l = new ArrayList<>();
        if (a == null) return l;
        if (a.length() > 2000) throw new IllegalArgumentException("lista");
        for (int i = 0; i < a.length(); i++) {
            String s = a.getString(i);
            if (!isPkg(s)) throw new IllegalArgumentException("pacote");
            if (!l.contains(s)) l.add(s);
        }
        return l;
    }

    private static ArrayList<Cat> parseCats(JSONArray a) throws Exception {
        ArrayList<Cat> l = new ArrayList<>();
        if (a == null) return l;
        if (a.length() > 100) throw new IllegalArgumentException("categorias");
        for (int i = 0; i < a.length(); i++) {
            JSONObject o = a.getJSONObject(i);
            String n = o.getString("name").trim();
            if (n.isEmpty() || n.length() > 64) throw new IllegalArgumentException("nome");
            Cat c = new Cat();
            c.name = n;
            c.apps.addAll(pkgList(o.optJSONArray("apps")));
            l.add(c);
        }
        return l;
    }

    private JSONArray catsJson() {
        JSONArray a = new JSONArray();
        try {
            for (Cat c : cats) {
                JSONObject o = new JSONObject();
                o.put("name", c.name);
                o.put("apps", new JSONArray(c.apps));
                a.put(o);
            }
        } catch (Exception ignored) { }
        return a;
    }

    private void toast(String s) {
        Toast.makeText(this, s, Toast.LENGTH_LONG).show();
    }

    // ------------------------------------------------------------------ proteccao de ecra

    private final Runnable saverRun = this::showSaver;

    /** Recomeca a contagem (cada tecla); 0 minutos = desligada. */
    private void resetSaver() {
        ui.removeCallbacks(saverRun);
        int m = prefs == null ? 0 : saverMinutes();
        if (m > 0) ui.postDelayed(saverRun, m * 60000L);
    }

    private void showSaver() {
        // com um dialogo aberto (ou o launcher tapado) nao aparece: volta a contar
        if (!hasWindowFocus() || movePkg != null) { resetSaver(); return; }
        if (saver == null) {
            saver = new FrameLayout(this);
            saver.setBackgroundColor(Color.BLACK);
            saverBox = new LinearLayout(this);
            saverBox.setOrientation(LinearLayout.VERTICAL);
            saverBox.setGravity(Gravity.CENTER_HORIZONTAL);
            saverClock = text("", 110, 0x59FFFFFF, false);
            saverClock.setTypeface(Typeface.create("sans-serif-thin", Typeface.NORMAL));
            saverClock.setIncludeFontPadding(false);
            saverDate = text("", 22, 0x40FFFFFF, false);
            saverBox.addView(saverClock);
            saverBox.addView(saverDate);
            saver.addView(saverBox, new FrameLayout.LayoutParams(-2, -2));
            root.addView(saver, new FrameLayout.LayoutParams(-1, -1));
        }
        ui.removeCallbacks(statusTick);   // nada a actualizar por baixo
        updateSaver();
        saver.setAlpha(0f);
        saver.setVisibility(View.VISIBLE);
        saver.bringToFront();
        saver.animate().alpha(1f).setDuration(600).start();
        saver.post(this::placeSaver);
    }

    private void hideSaver(boolean resume) {
        if (saver == null || saver.getVisibility() != View.VISIBLE) return;
        saver.animate().cancel();
        saver.setVisibility(View.GONE);
        if (resume) { ui.removeCallbacks(statusTick); statusTick.run(); updateClock(); }
    }

    private void updateSaver() {
        Date now = new Date();
        boolean h24 = android.text.format.DateFormat.is24HourFormat(this);
        saverClock.setText(new SimpleDateFormat(h24 ? "HH:mm" : "h:mm", I18n.locale()).format(now));
        String d = new SimpleDateFormat(I18n.s("date_fmt"), I18n.locale()).format(now);
        saverDate.setText(d.isEmpty() ? d : Character.toUpperCase(d.charAt(0)) + d.substring(1));
    }

    /** Posicao aleatoria (muda a cada minuto) para nao marcar o ecra. */
    private void placeSaver() {
        if (saver == null) return;
        int fw = saver.getWidth() - saverBox.getWidth(), fh = saver.getHeight() - saverBox.getHeight();
        java.util.Random r = new java.util.Random();
        saverBox.setTranslationX(fw > 0 ? r.nextInt(fw) : 0);
        saverBox.setTranslationY(fh > 0 ? r.nextInt(fh) : 0);
    }

    /** Chamado pelo TIME_TICK: novo minuto -> nova hora e nova posicao, com um fade curto. */
    private void saverMinute() {
        if (saver == null || saver.getVisibility() != View.VISIBLE) return;
        saverBox.animate().alpha(0f).setDuration(400).withEndAction(() -> {
            updateSaver();
            saverBox.post(() -> {
                placeSaver();
                saverBox.animate().alpha(1f).setDuration(400).start();
            });
        }).start();
    }

    /** I18n.s("about"): o logotipo de arranque como fundo, titulo, teclas e botao OK por cima. */
    private void showAbout() {
        final android.app.Dialog d = new android.app.Dialog(this, android.R.style.Theme_DeviceDefault_Dialog_NoActionBar);
        FrameLayout card = new FrameLayout(this);
        GradientDrawable bg = new GradientDrawable();
        bg.setCornerRadius(px(16));
        bg.setColor(0xFF0B0F17);
        card.setBackground(bg);
        card.setClipToOutline(true);

        ImageView logo = new ImageView(this);
        logo.setImageResource(R.drawable.about_logo);
        logo.setScaleType(ImageView.ScaleType.CENTER_CROP);
        card.addView(logo, new FrameLayout.LayoutParams(-1, -1));

        TextView title = text("A95X Z2 Home " + versionName(), 18, Color.WHITE, true);
        FrameLayout.LayoutParams tl = new FrameLayout.LayoutParams(-2, -2, Gravity.TOP | Gravity.START);
        tl.setMargins(px(24), px(18), 0, 0);
        card.addView(title, tl);

        TextView keys = text(I18n.s("about_keys"), 12, 0xB3FFFFFF, false);
        FrameLayout.LayoutParams kl = new FrameLayout.LayoutParams(-2, -2, Gravity.BOTTOM | Gravity.START);
        kl.setMargins(px(24), 0, 0, px(24));
        card.addView(keys, kl);

        TextView ok = pill("OK");
        ok.setOnClickListener(v -> d.dismiss());
        FrameLayout.LayoutParams ol = new FrameLayout.LayoutParams(-2, -2, Gravity.BOTTOM | Gravity.END);
        ol.setMargins(0, 0, px(20), px(16));
        card.addView(ok, ol);

        d.setContentView(card, new ViewGroup.LayoutParams(px(640), px(360)));
        // Sem isto o fundo da janela de dialogo do tema aparece nos cantos (contorno claro).
        Window dw = d.getWindow();
        if (dw != null) {
            dw.setBackgroundDrawable(new android.graphics.drawable.ColorDrawable(Color.TRANSPARENT));
            dw.addFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND);
            dw.setDimAmount(0.6f);
        }
        d.show();
        ok.requestFocus();
    }

    private String versionName() {
        try { return pm.getPackageInfo(getPackageName(), 0).versionName; } catch (Exception e) { return ""; }
    }

    private void menu(String title, List<String> opts, List<Runnable> acts) {
        menu(title, opts, acts, null);
    }

    /** onBack != null: VOLTAR no comando regressa ao menu anterior em vez de fechar tudo (1.4). */
    private void menu(String title, List<String> opts, List<Runnable> acts, Runnable onBack) {
        AlertDialog.Builder b = new AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
                .setTitle(title)
                .setItems(opts.toArray(new String[0]), (d, w) -> acts.get(w).run());
        if (onBack != null) b.setOnCancelListener(d -> onBack.run());
        b.show();
    }

    private void startSafe(Intent i) {
        try { startActivity(i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)); } catch (Exception ignored) { }
    }

    private void loadPrefs() {
        favs.clear();
        String f = prefs.getString("favs", "");
        if (!f.isEmpty()) favs.addAll(Arrays.asList(f.split(",")));
        hidden.clear();
        String h = prefs.getString("hidden", "");
        if (!h.isEmpty()) hidden.addAll(Arrays.asList(h.split(",")));
        appOrder.clear();
        String o = prefs.getString("order", "");
        if (!o.isEmpty()) appOrder.addAll(Arrays.asList(o.split(",")));
        sortMode = prefs.getString("sort", "az");
        recents.clear();
        String r = prefs.getString("recents", "");
        if (!r.isEmpty()) recents.addAll(Arrays.asList(r.split(",")));
        showRecents = prefs.getBoolean("show_recents", true);
        cats.clear();
        try { cats.addAll(parseCats(new JSONArray(prefs.getString("cats", "[]")))); } catch (Exception ignored) { }
    }

    private void savePrefs() {
        prefs.edit().putString("favs", TextUtils.join(",", favs))
                .putString("hidden", TextUtils.join(",", hidden))
                .putString("order", TextUtils.join(",", appOrder))
                .putString("sort", sortMode)
                .putString("cats", catsJson().toString()).apply();
    }

    // ------------------------------------------------------------------ estado (relogio, rede, temperatura)

    private void updateClock() {
        Date now = new Date();
        boolean h24 = android.text.format.DateFormat.is24HourFormat(this);
        clock.setText(new SimpleDateFormat(h24 ? "HH:mm" : "h:mm", I18n.locale()).format(now));
        String d = new SimpleDateFormat(I18n.s("date_fmt"), I18n.locale()).format(now);
        date.setText(d.isEmpty() ? d : Character.toUpperCase(d.charAt(0)) + d.substring(1));
    }

    private void updateStatus() {
        String label = I18n.s("no_network");
        int level = -1;   // -1 sem rede, 0..4 Wi-Fi, 5 cabo
        try {
            ConnectivityManager cm = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
            Network n = cm.getActiveNetwork();
            NetworkCapabilities nc = n == null ? null : cm.getNetworkCapabilities(n);
            if (nc != null && nc.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)) {
                label = I18n.s("ethernet"); level = 5;
            } else if (nc != null && nc.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) {
                WifiManager wm = (WifiManager) getApplicationContext().getSystemService(Context.WIFI_SERVICE);
                int rssi = wm.getConnectionInfo().getRssi();
                level = WifiManager.calculateSignalLevel(rssi, 5);
                label = I18n.s("wifi");
            }
        } catch (Exception ignored) { }
        net.setText(label);
        signal.setLevel(level);

        long[] m = readMem();   // kB: total, disponivel
        if (m[0] > 0) {
            float used = (m[0] - m[1]) / (float) m[0];   // fraccao em uso (o resto esta livre)
            ramIcon.setUsed(used);
            ram.setText(Math.round(used * 100) + "%");
            ram.setTextColor(used >= 0.85f ? 0xFFFF8A65 : 0xCCFFFFFF);
        }

        int t = readTemp();
        temp.setText(t > 0 ? t + " °C" : "");
        temp.setTextColor(t >= 80 ? 0xFFFF8A65 : 0xCCFFFFFF);
    }

    private long[] readMem() {
        long tot = 0, av = 0;
        try (BufferedReader r = new BufferedReader(new FileReader("/proc/meminfo"))) {
            String l;
            while ((l = r.readLine()) != null && (tot == 0 || av == 0)) {
                if (l.startsWith("MemTotal:")) tot = Long.parseLong(l.replaceAll("\\D+", ""));
                else if (l.startsWith("MemAvailable:")) av = Long.parseLong(l.replaceAll("\\D+", ""));
            }
        } catch (Exception ignored) { }
        return new long[]{tot, av};
    }

    private int readTemp() {
        try (BufferedReader r = new BufferedReader(new FileReader("/sys/class/thermal/thermal_zone0/temp"))) {
            int v = Integer.parseInt(r.readLine().trim());
            return v > 1000 ? v / 1000 : v;
        } catch (Exception e) {
            return -1;
        }
    }

    // ------------------------------------------------------------------ receivers

    private final BroadcastReceiver tick = new BroadcastReceiver() {
        @Override public void onReceive(Context c, Intent i) {
            if (saver != null && saver.getVisibility() == View.VISIBLE) { saverMinute(); return; }
            updateClock(); updateStatus();
        }
    };

    private final BroadcastReceiver netRx = new BroadcastReceiver() {
        @Override public void onReceive(Context c, Intent i) { updateStatus(); }
    };

    private final Runnable reloadLater = this::reloadApps;

    private final BroadcastReceiver pkgs = new BroadcastReceiver() {
        @Override public void onReceive(Context c, Intent i) {
            Uri u = i.getData();
            if (u != null) {
                String p = u.getSchemeSpecificPart();
                ArrayList<String> drop = new ArrayList<>();
                for (String k : art.keySet()) if (k.startsWith(p + "/")) drop.add(k);
                for (String k : drop) { art.remove(k); hasBanner.remove(k); }
            }
            ui.removeCallbacks(reloadLater);
            ui.postDelayed(reloadLater, 600);
        }
    };

    private void registerReceivers() {
        IntentFilter t = new IntentFilter(Intent.ACTION_TIME_TICK);
        t.addAction(Intent.ACTION_TIME_CHANGED);
        t.addAction(Intent.ACTION_TIMEZONE_CHANGED);
        registerReceiver(tick, t);

        IntentFilter n = new IntentFilter(ConnectivityManager.CONNECTIVITY_ACTION);
        n.addAction(WifiManager.RSSI_CHANGED_ACTION);
        n.addAction(WifiManager.NETWORK_STATE_CHANGED_ACTION);
        registerReceiver(netRx, n);

        IntentFilter p = new IntentFilter();
        p.addAction(Intent.ACTION_PACKAGE_ADDED);
        p.addAction(Intent.ACTION_PACKAGE_REMOVED);
        p.addAction(Intent.ACTION_PACKAGE_CHANGED);
        p.addAction(Intent.ACTION_PACKAGE_REPLACED);
        p.addDataScheme("package");
        registerReceiver(pkgs, p);
    }
}
