
#include <string>

#include <aws/core/Aws.h>

#include "redis.hpp"
#include "utils.hpp"

Redis::Redis(std::string redis_hostname, int redis_port)
{
  _context = redisConnect(redis_hostname.c_str(), redis_port);
  if (_context == nullptr || _context->err) {
    if (_context) {
      std::cerr << "Redis Error: " << _context->errstr << '\n';
    } else {
      std::cerr << "Can't allocate redis context\n";
    }
  }
}

bool Redis::is_initialized()
{
  return _context != nullptr;
}

Redis::~Redis()
{
  redisFree(_context);
}

uint64_t Redis::download_file(Aws::String const &key,
                        int &required_retries, bool with_backoff)
{
  std::string comm = "GET " + key;
    
  auto bef = timeSinceEpochMillisec();
  int retries = 0;
  const int MAX_RETRIES = 1500;

  while (retries < MAX_RETRIES) {

    redisReply* reply = (redisReply*) redisCommand(_context, comm.c_str());

    if (reply->type == REDIS_REPLY_NIL || reply->type == REDIS_REPLY_ERROR) {

      retries += 1;
      if(with_backoff) {
        int sleep_time = retries;
        if (retries > 100) {
            sleep_time = retries * 2;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(sleep_time));
      }

    } else {
      
      uint64_t finishedTime = timeSinceEpochMillisec();
      required_retries = retries;

      freeReplyObject(reply);
      return finishedTime - bef;

    }
    freeReplyObject(reply);
  }
  return 0;
}

uint64_t Redis::upload_file(Aws::String const &key,
                        int size, char* pBuf)
{
  std::string comm = "SET " + key + " %b";

  
  uint64_t bef = timeSinceEpochMillisec();
  redisReply* reply = (redisReply*) redisCommand(_context, comm.c_str(), pBuf, size);
  uint64_t finishedTime = timeSinceEpochMillisec();

  if (reply->type == REDIS_REPLY_NIL || reply->type == REDIS_REPLY_ERROR) {
    std::cerr << "Failed to write in Redis!" << std::endl;
    abort();
  }
  freeReplyObject(reply);

  return finishedTime - bef;
}

uint64_t Redis::delete_file(std::string const &key)
{
  std::string comm = "DEL " + key;

  uint64_t bef = timeSinceEpochMillisec();
  redisReply* reply = (redisReply*) redisCommand(_context, comm.c_str());
  uint64_t finishedTime = timeSinceEpochMillisec();

  if (reply->type == REDIS_REPLY_NIL || reply->type == REDIS_REPLY_ERROR) {
    std::cerr << "Couldn't delete the key!" << '\n';
    abort();
  }
  freeReplyObject(reply);

  return finishedTime - bef;
}

