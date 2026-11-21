package pt.a95xz2.updater;

import android.util.Base64;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.KeyFactory;
import java.security.MessageDigest;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.X509EncodedKeySpec;

/** Rede (HTTPS com redireccoes), SHA-256 e verificacao da assinatura do manifesto. */
final class Net {
    static final String UA = "A95XZ2-Updater/1.0";
    private static final int MAX_REDIRECTS = 6;

    /** Erro HTTP com o codigo (404 = ficheiro ainda nao publicado). */
    static final class HttpError extends IOException {
        final int code;
        HttpError(int code, String url) { super("HTTP " + code + " (" + url + ")"); this.code = code; }
    }

    interface Progress { void on(long done, long total); }

    /** Abre a ligacao seguindo redireccoes a mao (so https; GitHub -> objects.githubusercontent.com). */
    static HttpURLConnection open(String url) throws IOException {
        String u = url;
        for (int i = 0; i <= MAX_REDIRECTS; i++) {
            if (!u.startsWith("https://")) throw new IOException("URL nao https: " + u);
            HttpURLConnection c = (HttpURLConnection) new URL(u).openConnection();
            c.setInstanceFollowRedirects(false);
            c.setConnectTimeout(15000);
            c.setReadTimeout(30000);
            c.setUseCaches(false);
            c.setRequestProperty("User-Agent", UA);
            c.setRequestProperty("Accept-Encoding", "identity");   // bytes exactos (assinatura/sha256)
            int code = c.getResponseCode();
            if (code == 301 || code == 302 || code == 303 || code == 307 || code == 308) {
                String loc = c.getHeaderField("Location");
                c.disconnect();
                if (loc == null) throw new IOException("redireccao sem Location");
                u = new URL(new URL(u), loc).toString();
                continue;
            }
            if (code != 200) { c.disconnect(); throw new HttpError(code, u); }
            return c;
        }
        throw new IOException("demasiadas redireccoes");
    }

    /** GET pequeno para memoria (manifesto e assinatura), com limite de tamanho. */
    static byte[] get(String url, int max) throws IOException {
        HttpURLConnection c = open(url);
        try (InputStream in = c.getInputStream()) {
            ByteArrayOutputStream bo = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) {
                bo.write(buf, 0, n);
                if (bo.size() > max) throw new IOException("resposta demasiado grande");
            }
            return bo.toByteArray();
        } finally {
            c.disconnect();
        }
    }

    /** Transfere para ficheiro; para se passar do tamanho esperado (+1 byte ja e erro). */
    static void download(String url, File out, long expected, Progress p) throws IOException {
        HttpURLConnection c = open(url);
        try (InputStream in = c.getInputStream(); OutputStream os = new FileOutputStream(out)) {
            long total = expected > 0 ? expected : c.getContentLength();
            long done = 0, last = 0;
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) > 0) {
                if (Thread.currentThread().isInterrupted()) throw new IOException("cancelado");
                os.write(buf, 0, n);
                done += n;
                if (expected > 0 && done > expected) throw new IOException("ficheiro maior que o esperado");
                if (done - last > 256 * 1024) { last = done; p.on(done, total); }
            }
            p.on(done, total);
        } finally {
            c.disconnect();
        }
    }

    static String sha256(File f) throws IOException {
        try (InputStream in = new FileInputStream(f)) {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) > 0) md.update(buf, 0, n);
            return hex(md.digest());
        } catch (java.security.NoSuchAlgorithmException e) {
            throw new IOException(e);
        }
    }

    static String hex(byte[] b) {
        StringBuilder sb = new StringBuilder(b.length * 2);
        for (byte x : b) sb.append(String.format("%02x", x & 0xff));
        return sb.toString();
    }

    /** Assinatura = base64 de SHA256withRSA (PKCS#1 v1.5) sobre os bytes exactos do JSON. */
    static boolean verify(byte[] data, byte[] sigB64, byte[] pubDer) {
        try {
            byte[] sig = Base64.decode(new String(sigB64, "US-ASCII").trim(), Base64.DEFAULT);
            PublicKey k = KeyFactory.getInstance("RSA").generatePublic(new X509EncodedKeySpec(pubDer));
            Signature s = Signature.getInstance("SHA256withRSA");
            s.initVerify(k);
            s.update(data);
            return s.verify(sig);
        } catch (Exception e) {
            return false;
        }
    }

    static byte[] readAll(InputStream in) throws IOException {
        ByteArrayOutputStream bo = new ByteArrayOutputStream();
        byte[] buf = new byte[4096];
        int n;
        while ((n = in.read(buf)) > 0) bo.write(buf, 0, n);
        return bo.toByteArray();
    }
}
