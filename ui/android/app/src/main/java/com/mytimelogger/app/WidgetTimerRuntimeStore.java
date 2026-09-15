package com.mytimelogger.app;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class WidgetTimerRuntimeStore {
    private static final String PREFS = "mtl_widget_runtime_v1", VALUE = "runtime", ALIAS = "mtl.widget.runtime.aes.v1";
    interface Backend { String read(); boolean write(String value); void clear(); }
    interface Crypto { String encrypt(String value) throws Exception; String decrypt(String value) throws Exception; void clear() throws Exception; }
    public static final class Config {
        public final String serverUrl, authToken, deviceId, verifiedUserId; public final long generation;
        Config(String url, String token, String device, String user, long generation) {
            this.serverUrl = url; this.authToken = token; this.deviceId = device; this.verifiedUserId = user; this.generation = generation;
        }
    }
    private final Backend backend; private final Crypto crypto;
    public WidgetTimerRuntimeStore(Context context) { this(new PreferenceBackend(context), new KeystoreCrypto()); }
    WidgetTimerRuntimeStore(Backend backend, Crypto crypto) { this.backend = backend; this.crypto = crypto; }

    public synchronized boolean configure(String raw) {
        try {
            Config value = parse(raw); if (value == null) return false;
            String envelope = value.generation + "." + crypto.encrypt(canonical(value));
            return backend.write(envelope);
        } catch (Exception ignored) { return false; }
    }
    public synchronized Config read() {
        try {
            String envelope = backend.read(); if (envelope == null) return null;
            int separator = envelope.indexOf('.'); if (separator < 1) return null;
            long generation = Long.parseLong(envelope.substring(0, separator));
            Config value = parse(crypto.decrypt(envelope.substring(separator + 1)));
            return value != null && value.generation == generation ? value : null;
        } catch (Exception ignored) { return null; }
    }
    public synchronized void clear() {
        backend.clear(); try { crypto.clear(); } catch (Exception ignored) { }
    }
    private static Config parse(String raw) {
        try {
            JsonObject json = JsonParser.parseString(raw).getAsJsonObject();
            Set<String> fields = json.keySet();
            if (!fields.equals(new HashSet<>(Arrays.asList("serverUrl", "authToken", "deviceId", "verifiedUserId", "generation")))) return null;
            String url = json.get("serverUrl").getAsString().trim().replaceAll("/+$", "");
            URI uri = URI.create(url); String token = json.get("authToken").getAsString();
            String device = json.get("deviceId").getAsString().trim(), user = json.get("verifiedUserId").getAsString().trim(); long generation = json.get("generation").getAsLong();
            if (!("http".equals(uri.getScheme()) || "https".equals(uri.getScheme())) || uri.getHost() == null
                    || token.trim().isEmpty() || device.isEmpty() || user.isEmpty() || generation < 1) return null;
            return new Config(url, token, device, user, generation);
        } catch (Exception ignored) { return null; }
    }
    private static String canonical(Config value) {
        JsonObject json = new JsonObject(); json.addProperty("serverUrl", value.serverUrl); json.addProperty("authToken", value.authToken);
        json.addProperty("deviceId", value.deviceId); json.addProperty("verifiedUserId", value.verifiedUserId); json.addProperty("generation", value.generation); return json.toString();
    }
    private static final class PreferenceBackend implements Backend {
        private final SharedPreferences values; PreferenceBackend(Context context) { values = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE); }
        public String read() { return values.getString(VALUE, null); }
        public boolean write(String value) { return values.edit().putString(VALUE, value).commit(); }
        public void clear() { values.edit().remove(VALUE).commit(); }
    }
    private static final class KeystoreCrypto implements Crypto {
        private SecretKey key() throws Exception {
            KeyStore store = KeyStore.getInstance("AndroidKeyStore"); store.load(null);
            if (store.containsAlias(ALIAS)) return ((KeyStore.SecretKeyEntry) store.getEntry(ALIAS, null)).getSecretKey();
            KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
            generator.init(new KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
            return generator.generateKey();
        }
        public String encrypt(String value) throws Exception {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.ENCRYPT_MODE, key());
            return Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP) + ":" + Base64.encodeToString(cipher.doFinal(value.getBytes(StandardCharsets.UTF_8)), Base64.NO_WRAP);
        }
        public String decrypt(String value) throws Exception {
            String[] parts = value.split(":", 2); if (parts.length != 2) throw new IllegalArgumentException();
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, Base64.decode(parts[0], Base64.NO_WRAP)));
            return new String(cipher.doFinal(Base64.decode(parts[1], Base64.NO_WRAP)), StandardCharsets.UTF_8);
        }
        public void clear() throws Exception { KeyStore store = KeyStore.getInstance("AndroidKeyStore"); store.load(null); if (store.containsAlias(ALIAS)) store.deleteEntry(ALIAS); }
    }
}
