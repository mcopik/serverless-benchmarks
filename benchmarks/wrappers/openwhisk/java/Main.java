import com.google.gson.JsonObject;
import com.example.project.App ;
import java.time.Instant;
import java.time.Duration;
import java.io.File;
import java.io.IOException;


public class Main {
    public static JsonObject main(JsonObject args) {

        // Logger logger = Logger.getLogger(FunctionHandler.class.getName());
        // logger.setLevel(Level.INFO);
        
        Gson gson = new Gson();
        App function = new App();

        Instant begin = Instant.now();
        JsonObject result = function.handler(args);
        Instant end = Instant.now();

        long computeTime = Duration.between(begin, end).toNanos() / 1000; // Convert nanoseconds to microseconds

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
        jsonObject.put("begin", formattedBegin); 
        jsonObject.put("end", formattedEnd);
        jsonObject.put("request_id", "requestId");  
        jsonObject.put("compute_time", computeTime);
        jsonObject.put("is_cold", isCold);
        jsonObject.put("result", result);
        return jsonResult;
    }
}

        
        