package com.mytimelogger.app;

import static org.junit.Assert.*;
import org.junit.Test;

public class SleepAutomationSecretStoreTest {
    @Test public void ciphertextHidesTokenAndClearRemovesIt() {
        String[] cell={null}; boolean[] cleared={false};
        SleepAutomationSecretStore.Values values=new SleepAutomationSecretStore.Values(){public String get(){return cell[0];}public void put(String v){cell[0]=v;}public void clear(){cell[0]=null;}};
        SleepAutomationSecretStore.Codec codec=new SleepAutomationSecretStore.Codec(){public String encrypt(String v){return new StringBuilder(v).reverse().toString();}public String decrypt(String v){return new StringBuilder(v).reverse().toString();}public void clear(){cleared[0]=true;}};
        SleepAutomationSecretStore store=new SleepAutomationSecretStore(values,codec); store.save("https://server","private-token");
        assertFalse(cell[0].contains("private-token")); assertArrayEquals(new String[]{"https://server","private-token"},store.read());
        store.clear(); assertNull(store.read()); assertTrue(cleared[0]);
    }
}
