package util;


/**
 * Class for testing. Provides a constant key. DO NOT ADOPT THIS FOR ANY REAL
 * PRODUCTION WORKLOAD!
 *
 * @author Joakim von Kistowski
 *
 */
public class ConstantKeyProvider implements IKeyProvider {

    /**
     * {@inheritDoc}
     */
    @Override
    public String getKey(SessionBlob blob) {
        return "thebestsecretkey";
    }

}
