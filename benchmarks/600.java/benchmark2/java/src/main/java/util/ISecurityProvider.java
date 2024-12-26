package util;


/**
 * Utilities for securing (e.g. encrypting) session blobs.
 *
 * @author Joakim von Kistowski
 *
 */
public interface ISecurityProvider {

    /**
     * Get the key provider for this security provider.
     *
     * @return The key provider.
     */
    public IKeyProvider getKeyProvider();

    /**
     * Secures a session blob. May encrypt or hash values within the blob.
     *
     * @param blob
     *          The blob to secure.
     * @return A secure blob to be passed on to the web ui.
     */
    public SessionBlob secure(SessionBlob blob);

    /**
     * Validates a secured session blob. Returns a valid and readable (e.g.
     * decrypted) blob. Returns null for invalid blobs.
     *
     * @param blob
     *          The blob to secure.
     * @return The valid and readable (e.g. decrypted) blob. Returns null for
     *         invalid blobs.
     */
    public SessionBlob validate(SessionBlob blob);

}
