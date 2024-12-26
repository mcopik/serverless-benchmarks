package utils;
import java.util.HashMap;
import java.util.Map;

/**
 * Objects of this class holds a mapping of {@link Product} IDs to quantities
 * that were bought in the same {@link Order} by one {@link User}. Non-present
 * {@link Product} IDs imply a quantity of 0.
 *
 * @author Johannes Grohmann
 *
 */
public class OrderItemSet {

    /**
     * Standard constructor.
     */
    public OrderItemSet() {
        orderset = new HashMap<>();
    }

    /**
     * The user that made this order.
     */
    private long userId;

    /**
     * The orderId that the Items were bought in.
     */
    private long orderId;

    /**
     * The productIds that were bought together with the given quantity.
     */
    private Map<Long, Integer> orderset;

    /**
     * @return the orderset
     */
    public Map<Long, Integer> getOrderset() {
        return orderset;
    }

    /**
     * @param orderset
     *            the orderset to set
     */
    public void setOrderset(Map<Long, Integer> orderset) {
        this.orderset = orderset;
    }

    /**
     * @return the orderId
     */
    public long getOrderId() {
        return orderId;
    }

    /**
     * @param orderId
     *            the orderId to set
     */
    public void setOrderId(long orderId) {
        this.orderId = orderId;
    }

    /**
     * @return the userId
     */
    public long getUserId() {
        return userId;
    }

    /**
     * @param userId the userId to set
     */
    public void setUserId(long userId) {
        this.userId = userId;
    }
}
