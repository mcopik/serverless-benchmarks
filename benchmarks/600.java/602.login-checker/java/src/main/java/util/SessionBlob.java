package util;

import java.util.LinkedList;
import java.util.List;

/**
 * Blob containing all information about the user session.
 * @author Simon
 */
public class SessionBlob {

    private Long uid;
    private String sid;
    private String token;
    private Order order;
    private List<OrderItem> orderItems = new LinkedList<OrderItem>();
    private String message;

    /**
     * Constructor, creates an empty order.
     */
    public SessionBlob() {
        this.setOrder(new Order());
    }

    /**
     * Getter for the userid.
     * @return userid
     */
    public Long getUID() {
        return uid;
    }

    /**
     * Setter for the userid.
     * @param uID userid
     */
    public void setUID(Long uID) {
        uid = uID;
    }

    /**
     * Getter for session id.
     * @return session id
     */
    public String getSID() {
        return sid;
    }

    /**
     * Setter for session id.
     * @param sID session id
     */
    public void setSID(String sID) {
        sid = sID;
    }

    /**
     * Getter for trust token.
     * @return trust token
     */
    public String getToken() {
        return token;
    }

    /**
     * Setter for trust token.
     * @param token trust token.
     */
    public void setToken(String token) {
        this.token = token;
    }

    /**
     * Setter for the message.
     * @param message String
     */
    public void setMessage(String message) {
        this.message = message;
    }

    /**
     * Getter for the message.
     * @return message
     */
    public String getMessage() {
        return message;
    }

    /**
     * Getter for order.
     * @return order
     */
    public Order getOrder() {
        return order;
    }

    /**
     * Setter for order.
     * @param order order
     */
    public void setOrder(Order order) {
        this.order = order;
    }

    /**
     * Getter for order items.
     * @return order items.
     */
    public List<OrderItem> getOrderItems() {
        return orderItems;
    }

    /**
     * Setter for order items.
     * @param orderItems list of order items
     */
    public void setOrderItems(List<OrderItem> orderItems) {
        this.orderItems = orderItems;
    }

    @Override
    public String toString() {
        return "ClassName{" +
                "uid=" + uid +
                ", sid='" + sid + '\'' +
                ", token='" + token + '\'' +
                ", order=" + (order != null ? order.toString() : "null") +
                ", orderItems=" + (orderItems != null ? orderItems.toString() : "null") +
                ", message='" + message + '\'' +
                '}';
    }
}
