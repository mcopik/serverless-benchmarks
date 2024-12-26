
package util;

/**
 * Provides keys for the security provider. The key provider must ensure that
 * keys accross replicated stores are consistent.
 *
 * @author Joakim von Kistowski
 *
 */
public interface IKeyProvider {

    /**
     * Returns a key for a session blob. Key must be the same, regardless of the
     * store instance upon which this call is made.
     *
     * @param blob
     *          The blob to secure.
     * @return The key.
     */
    public String getKey(SessionBlob blob);

}
