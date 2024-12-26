/**
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package utils;

/**
 * Entity for orders.
 *
 * @author Joakim von Kistowski
 *
 */
public class Order {

    private long id;
    private long userId;
    private String time;

    private long totalPriceInCents;
    private String addressName;
    private String address1;
    private String address2;

    private String creditCardCompany;
    private String creditCardNumber;
    private String creditCardExpiryDate;

    /**
     * Create a new and empty order.
     */
    public Order() {

    }

    /**
     * Every entity needs a copy constructor.
     *
     * @param order
     *          The order to copy.
     */
    public Order(Order order) {
        setId(order.getId());
        setUserId(order.getUserId());
        setTime(order.getTime());
        setTotalPriceInCents(order.getTotalPriceInCents());
        setAddressName(order.getAddressName());
        setAddress1(order.getAddress1());
        setAddress2(order.getAddress2());
        setCreditCardCompany(order.getCreditCardCompany());
        setCreditCardNumber(order.getCreditCardNumber());
        setCreditCardExpiryDate(order.getCreditCardExpiryDate());
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
     * Get the User id.
     *
     * @return the userId.
     */
    public long getUserId() {
        return userId;
    }

    /**
     * Set the User Id.
     *
     * @param userId
     *          the userId to set.
     */
    public void setUserId(long userId) {
        this.userId = userId;
    }

    /**
     * Get the time of order (ISO formatted). Formatted using {@link DateTimeFormatter.ISO_LOCAL_DATE_TIME}.
     *
     * @return the time.
     */
    public String getTime() {
        return time;
    }

    /**
     * Set the time of order (ISO formatted). Format using {@link DateTimeFormatter.ISO_LOCAL_DATE_TIME}.
     *
     * @param time
     *          the time to set.
     */
    public void setTime(String time) {
        this.time = time;
    }

    /**
     * Get the total price in cents.
     *
     * @return the totalPriceInCents.
     */
    public long getTotalPriceInCents() {
        return totalPriceInCents;
    }

    /**
     * Set the total price in cents.
     *
     * @param totalPriceInCents
     *          the totalPriceInCents to set.
     */
    public void setTotalPriceInCents(long totalPriceInCents) {
        this.totalPriceInCents = totalPriceInCents;
    }

    /**
     * Get the name for the address.
     *
     * @return the addressName.
     */
    public String getAddressName() {
        return addressName;
    }

    /**
     * Set the name for the address.
     *
     * @param addressName
     *          the addressName to set.
     */
    public void setAddressName(String addressName) {
        this.addressName = addressName;
    }

    /**
     * Get address line 1.
     *
     * @return the address1.
     */
    public String getAddress1() {
        return address1;
    }

    /**
     * Set address line 1.
     *
     * @param address1
     *          the address1 to set.
     */
    public void setAddress1(String address1) {
        this.address1 = address1;
    }

    /**
     * Get address line 2.
     *
     * @return the address2.
     */
    public String getAddress2() {
        return address2;
    }

    /**
     * Set address line 2.
     *
     * @param address2
     *          the address2 to set.
     */
    public void setAddress2(String address2) {
        this.address2 = address2;
    }

    /**
     * Get the name of the credit card company.
     *
     * @return the creditCardCompany.
     */
    public String getCreditCardCompany() {
        return creditCardCompany;
    }

    /**
     * Set the name of the credit card company.
     *
     * @param creditCardCompany
     *          the creditCardCompany to set.
     */
    public void setCreditCardCompany(String creditCardCompany) {
        this.creditCardCompany = creditCardCompany;
    }

    /**
     * Get the credit card number.
     *
     * @return the creditCardNumber.
     */
    public String getCreditCardNumber() {
        return creditCardNumber;
    }

    /**
     * Set the credit card number.
     *
     * @param creditCardNumber
     *          the creditCardNumber to set.
     */
    public void setCreditCardNumber(String creditCardNumber) {
        this.creditCardNumber = creditCardNumber;
    }

    /**
     * Get the credit card expiry date (ISO formatted). Formatted using {@link DateTimeFormatter.ISO_LOCAL_DATE}.
     *
     * @return the creditCardExpiryDate.
     */
    public String getCreditCardExpiryDate() {
        return creditCardExpiryDate;
    }

    /**
     * Set the credit card expiry date (ISO formatted). Format using {@link DateTimeFormatter.ISO_LOCAL_DATE}.
     *
     * @param creditCardExpiryDate
     *          the creditCardExpiryDate to set.
     */
    public void setCreditCardExpiryDate(String creditCardExpiryDate) {
        this.creditCardExpiryDate = creditCardExpiryDate;
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
        result = prime * result + (int) (userId ^ (userId >>> 32));
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
        Order other = (Order) obj;
        if (id != other.id) {
            return false;
        }
        if (userId != other.userId) {
            return false;
        }
        return true;
    }

}
