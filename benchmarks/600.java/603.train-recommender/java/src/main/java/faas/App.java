package faas;
import com.google.gson.*;
import utils.Order;
import utils.OrderItem;
import utils.OrderItemSet;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Map.Entry;
import java.util.Set;
import java.util.HashSet;
import java.util.HashMap;

public class App {


    private static boolean trainingFinished = false;

    public static final int MAX_NUMBER_OF_RECOMMENDATIONS = 10;



        public static JsonObject handler(JsonObject args) {
            Gson gson = new Gson();
            JsonObject jsonResult = new JsonObject();
            // Deserialize JSON input to Lists of OrderItem and Order
            JsonArray orderItemsArray = args.getAsJsonArray("orderItems");
            JsonArray ordersArray = args.getAsJsonArray("orders");

            List<OrderItem> orderItems = new ArrayList<>();
            for (JsonElement element : orderItemsArray) {
                orderItems.add(gson.fromJson(element, OrderItem.class));
            }

            List<Order> orders = new ArrayList<>();
            for (JsonElement element : ordersArray) {
                orders.add(gson.fromJson(element, Order.class));
            }
            Map<Long, Map<Long, Double>> userBuyingMatrix;
            Map<Long, Set<OrderItemSet>> userItemSets;
            Set<Long> totalProducts;
            long tic = System.currentTimeMillis();
            totalProducts = new HashSet<>();
            // first create order mapping unorderized
            Map<Long, OrderItemSet> unOrderizeditemSets = new HashMap<>();
            for (OrderItem orderItem : orderItems) {
                if (!unOrderizeditemSets.containsKey(orderItem.getOrderId())) {
                    unOrderizeditemSets.put(orderItem.getOrderId(), new OrderItemSet());
                    unOrderizeditemSets.get(orderItem.getOrderId()).setOrderId(orderItem.getOrderId());
                }
                unOrderizeditemSets.get(orderItem.getOrderId()).getOrderset().put(orderItem.getProductId(),
                        orderItem.getQuantity());
                // see, if we already have our item
                if (!totalProducts.contains(orderItem.getProductId())) {
                    // if not known yet -> add
                    totalProducts.add(orderItem.getProductId());
                }
            }
            // now map each id with the corresponding order
            Map<Order, OrderItemSet> itemSets = new HashMap<>();
            for (Long orderid : unOrderizeditemSets.keySet()) {
                Order realOrder = findOrder(orders, orderid);
                itemSets.put(realOrder, unOrderizeditemSets.get(orderid));
            }
            userItemSets = new HashMap<>();
            for (Order order : itemSets.keySet()) {
                if (!userItemSets.containsKey(order.getUserId())) {
                    userItemSets.put(order.getUserId(), new HashSet<OrderItemSet>());
                }
                itemSets.get(order).setUserId(order.getUserId());
                userItemSets.get(order.getUserId()).add(itemSets.get(order));
            }
            userBuyingMatrix = createUserBuyingMatrix(userItemSets);
            executePreprocessing();
            trainingFinished = true;
            jsonResult.addProperty("trainingFinished", trainingFinished);
            return jsonResult;
        }
    protected static void executePreprocessing() {
        // do nothing
    }

    private static Order findOrder(List<Order> orders, long orderid) {
        for (Order order : orders) {
            if (order.getId() == orderid) {
                return order;
            }
        }
        return null;
    }

    private static Map<Long, Map<Long, Double>> createUserBuyingMatrix(Map<Long, Set<OrderItemSet>> useritemsets) {
        Map<Long, Map<Long, Double>> matrix = new HashMap<>();
        // for each user
        for (Map.Entry<Long, Set<OrderItemSet>> entry : useritemsets.entrySet()) {
            // create a new line for this user-ID
            Map<Long, Double> line = new HashMap<>();
            // for all orders of that user
            for (OrderItemSet orderset : entry.getValue()) {
                // for all orderitems of that orderset
                for (Entry<Long, Integer> product : orderset.getOrderset().entrySet()) {
                    // if key was not known before -> first occurence
                    if (!line.containsKey(product.getKey())) {
                        line.put(product.getKey(), Double.valueOf(product.getValue()));
                    } else {
                        // if key was known before -> increase counter
                        line.put(product.getKey(), Double.valueOf(line.get(product.getKey()) + product.getValue()));
                    }
                }
            }
            // add this user-ID to the matrix
            matrix.put(entry.getKey(), line);
        }
        return matrix;
    }

    }
//}
