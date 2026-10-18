package com.mytimelogger.app;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.nio.ByteBuffer;
import java.security.KeyStore;
import javax.crypto.*;
import javax.crypto.spec.GCMParameterSpec;

final class SleepAutomationSecretStore {
    interface Values { String get(); void put(String value); void clear(); }
    interface Codec { String encrypt(String value) throws Exception; String decrypt(String value) throws Exception; void clear() throws Exception; }
    private final Values values; private final Codec codec;
    SleepAutomationSecretStore(Context c) { this(new Values(){ public String get(){return c.getSharedPreferences("sleep-automation-secret",0).getString("active",null);} public void put(String v){c.getSharedPreferences("sleep-automation-secret",0).edit().putString("active",v).commit();} public void clear(){c.getSharedPreferences("sleep-automation-secret",0).edit().clear().commit();}}, new AndroidCodec()); }
    SleepAutomationSecretStore(Values values, Codec codec) { this.values=values; this.codec=codec; }
    void save(String url,String token) { try { values.put(codec.encrypt(url+"\n"+token)); } catch(Exception ignored) { values.clear(); } }
    String[] read() { try { String raw=values.get(); return raw==null?null:codec.decrypt(raw).split("\n",2); } catch(Exception ignored) { values.clear(); return null; } }
    void clear() { values.clear(); try { codec.clear(); } catch(Exception ignored) {} }
    static final class AndroidCodec implements Codec {
        static final String ALIAS="mtl-sleep-automation"; KeyStore store() throws Exception { KeyStore k=KeyStore.getInstance("AndroidKeyStore"); k.load(null); return k; }
        SecretKey key() throws Exception { KeyStore k=store(); if(k.containsAlias(ALIAS)) return (SecretKey)k.getKey(ALIAS,null); KeyGenerator g=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore"); g.init(new KeyGenParameterSpec.Builder(ALIAS,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT).setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build()); return g.generateKey(); }
        public String encrypt(String v)throws Exception{Cipher c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.ENCRYPT_MODE,key());byte[] e=c.doFinal(v.getBytes("UTF-8")),iv=c.getIV();return Base64.encodeToString(ByteBuffer.allocate(4+iv.length+e.length).putInt(iv.length).put(iv).put(e).array(),Base64.NO_WRAP);}
        public String decrypt(String v)throws Exception{ByteBuffer b=ByteBuffer.wrap(Base64.decode(v,Base64.NO_WRAP));byte[] iv=new byte[b.getInt()],e=new byte[b.remaining()-iv.length];b.get(iv);b.get(e);Cipher c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.DECRYPT_MODE,key(),new GCMParameterSpec(128,iv));return new String(c.doFinal(e),"UTF-8");}
        public void clear()throws Exception{store().deleteEntry(ALIAS);}
    }
}
