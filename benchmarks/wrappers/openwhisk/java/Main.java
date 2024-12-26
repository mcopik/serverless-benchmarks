import faas.App;
import com.google.gson.Gson;
import com.google.gson.JsonObject;
import util.SessionBlob;
import util.ShaSecurityProvider;
import java.time.Instant;
import java.time.Duration;
import java.io.File;
import java.io.IOException;
//import jakarta.ws.rs.core.Response;


public class Main {
    public static JsonObject main(JsonObject args) {

        // Logger logger = Logger.getLogger(FunctionHandler.class.getName());
        // logger.setLevel(Level.INFO);
        
        Gson gson = new Gson();
        App function = new App();

        long start_nano = System.nanoTime();

        Instant begin = Instant.now();
        JsonObject result = function.handler(args);
        Instant end = Instant.now();

        long end_nano = System.nanoTime();

        // long computeTime = Duration.between(begin, end).toNanos() / 1000; // Convert nanoseconds to microseconds

        long computeTime = end_nano - start_nano;
        boolean isCold = false;
        String fileName = "/cold_run"; 

        File file = new File(fileName);
        if (!file.exists()) {
            isCold = true;
            try {
                file.createNewFile();
            } catch (IOException e) {
                e.printStackTrace();
            }
        }

        // Convert to Unix timestamp in seconds.microseconds
        String formattedBegin = String.format("%d.%06d", begin.getEpochSecond(), begin.getNano() / 1000); // Convert nanoseconds to microseconds
        String formattedEnd = String.format("%d.%06d", end.getEpochSecond(), end.getNano() / 1000);

        String requestId = System.getenv("__OW_ACTIVATION_ID");  

        JsonObject jsonResult = new JsonObject();
        jsonResult.addProperty("begin", formattedBegin); 
        jsonResult.addProperty("end", formattedEnd);
        jsonResult.addProperty("request_id", requestId);  
        jsonResult.addProperty("compute_time", computeTime);
        jsonResult.addProperty("is_cold", isCold);
        jsonResult.addProperty("result", result.toString());
        return jsonResult;
    }

}
