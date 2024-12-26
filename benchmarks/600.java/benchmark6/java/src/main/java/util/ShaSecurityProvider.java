package util;

import java.io.UnsupportedEncodingException;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.net.URLEncoder;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

/**
 * Secruity provider uscom.fasterxml.jackson.databind.Objecting AES.
 *
 * @author Simon
 *
 */
public class ShaSecurityProvider implements ISecurityProvider {

    @Override
    public IKeyProvider getKeyProvider() {
        return new ConstantKeyProvider();
    }

    @Override
    public SessionBlob secure(SessionBlob blob) {
        if (blob.getUID() == null || blob.getSID() == null) {
            return blob;
        }
        blob.setToken(null);
        String blobString = blobToString(blob);
        blob.setToken(getSha512(blobString));
        return blob;
    }

    private String blobToString(SessionBlob blob) {
        ObjectMapper o = new ObjectMapper();
        try {
            return URLEncoder.encode(o.writeValueAsString(blob), "UTF-8");
        } catch (JsonProcessingException | UnsupportedEncodingException e)
        {
            throw new IllegalStateException("Could not save blob!");
        }
    }

    @Override
    public SessionBlob validate(SessionBlob blob) {
        if (blob.getToken() == null) {
            return null;
        }

        String token = blob.getToken();
        blob.setToken(null);
        String blobString = blobToString(blob);
        String validationToken = getSha512(blobString);
        if (validationToken.equals(token)) {
            return blob;
        }
        return null;
    }

    private String getSha512(String passwordToHash) {
        String generatedPassword = null;
        try {
            String salt = getKeyProvider().getKey(null);
            MessageDigest md = MessageDigest.getInstance("SHA-512");
            md.update(salt.getBytes("UTF-8"));
            byte[] bytes = md.digest(passwordToHash.getBytes("UTF-8"));
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < bytes.length; i++) {
                sb.append(Integer.toString((bytes[i] & 0xff) + 0x100, 16).substring(1));
            }
            generatedPassword = sb.toString();
        } catch (NoSuchAlgorithmException | UnsupportedEncodingException e) {
            e.printStackTrace();
        }
        return generatedPassword;
    }
}
