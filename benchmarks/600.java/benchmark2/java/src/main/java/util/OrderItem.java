
package util;

/**
 * Entity Class for OrderItems (item with quantity in shopping cart or order).
 *
 * @author Joakim von Kistowski
 *
 */
public class OrderItem {

    private long id;
    private long productId;
    private long orderId;
    private int quantity;
    private long unitPriceInCents;

    /**
     * Create a new and empty OrderItem.
     */
    public OrderItem() {

    }

    /**
     * Every Entity needs a Copy-Constructor!
     *
     * @param orderItem
     *          The entity to Copy.
     */
    public OrderItem(OrderItem orderItem) {
        setId(orderItem.getId());
        setProductId(orderItem.getProductId());
        setOrderId(orderItem.getOrderId());
        setQuantity(orderItem.getQuantity());
        setUnitPriceInCents(orderItem.getUnitPriceInCents());
    }

    /**
     * Get the id (remember that this ID may be incorrect, especially if a separate id was passed).
     *
     * @return The id.
     */
    public long getId() {
        return id;
    }

    /**
     * For REST use only. Sets the ID. Ignored by persistence.
     *
     * @param id
     *          ID, as passed by the REST API.
     */
    public void setId(long id) {
        this.id = id;
    }

    /**
     * ID of the order item's product.
     *
     * @return Product Id;
     */
    public long getProductId() {
        return productId;
    }

    /**
     * Sets the ID of the order item's product. Every order Item MUST have a valid product ID.
     *
     * @param productId
     *          The product ID to set.
     */
    public void setProductId(long productId) {
        this.productId = productId;
    }

    /**
     * Get the quantity (amount in shopping cart/order).
     *
     * @return The quantity.
     */
    public int getQuantity() {
        return quantity;
    }

    /**
     * Set the quantity (amount in shopping cart/order).
     *
     * @param quantity
     *          The quantity.
     */
    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }

    /**
     * The price per single item in the order item.
     *
     * @return Price per single item.
     */
    public long getUnitPriceInCents() {
        return unitPriceInCents;
    }

    /**
     * Set the price per single item in the order item.
     *
     * @param unitPriceInCents
     *          Price per single item.
     */
    public void setUnitPriceInCents(long unitPriceInCents) {
        this.unitPriceInCents = unitPriceInCents;
    }

    /**
     * Gets the ID of the order item's order.
     *
     * @return The order ID.
     */
    public long getOrderId() {
        return orderId;
    }

    /**
     * Sets the ID of the order item's order. Persistence requires that every order item MUST have a valid order ID. For
     * persistence the order must already exist in database.
     *
     * @param orderId
     *          The order ID to set.
     */
    public void setOrderId(long orderId) {
        this.orderId = orderId;
    }

    /*
     * (non-Javadoc)
     *
     * @see java.lang.Object#hashCode()
     */
    @Override
    public int hashCode() {
        final int prime = 31;
        int result = 1;
        result = prime * result + (int) (id ^ (id >>> 32));
        result = prime * result + (int) (orderId ^ (orderId >>> 32));
        result = prime * result + (int) (productId ^ (productId >>> 32));
        return result;
    }

    /*
     * (non-Javadoc)
     *
     * @see java.lang.Object#equals(java.lang.Object)
     */
    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (obj == null) {
            return false;
        }
        if (getClass() != obj.getClass()) {
            return false;
        }
        OrderItem other = (OrderItem) obj;
        if (id != other.id) {
            return false;
        }
        if (orderId != other.orderId) {
            return false;
        }
        if (productId != other.productId) {
            return false;
        }
        return true;
    }

}
