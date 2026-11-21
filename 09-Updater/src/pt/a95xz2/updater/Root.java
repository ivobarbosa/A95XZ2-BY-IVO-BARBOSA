package pt.a95xz2.updater;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;

/** Comandos como root via Magisk: su -c <cmd>, stdout+stderr juntos, linha a linha. */
final class Root {
    interface Lines { void line(String s); }

    /** Devolve o codigo de saida; IOException se o su nao existir. */
    static int run(String cmd, Lines out) throws IOException {
        Process p = new ProcessBuilder("su", "-c", cmd).redirectErrorStream(true).start();
        try {
            p.getOutputStream().close();
            BufferedReader r = new BufferedReader(new InputStreamReader(p.getInputStream(), "UTF-8"));
            String l;
            while ((l = r.readLine()) != null) if (out != null) out.line(l);
            return p.waitFor();
        } catch (InterruptedException e) {
            p.destroy();
            Thread.currentThread().interrupt();
            throw new IOException("interrompido");
        }
    }

    /** true se o su existe e esta autorizado para esta app (uid 0). */
    static boolean available() {
        final StringBuilder sb = new StringBuilder();
        try {
            int rc = run("id -u", sb::append);
            return rc == 0 && sb.toString().trim().equals("0");
        } catch (IOException e) {
            return false;
        }
    }

    /** Aspas simples para sh. */
    static String q(String s) { return "'" + s.replace("'", "'\\''") + "'"; }
}
