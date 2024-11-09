mkdir /tmp/redis
docker run --rm -d -p 6379:6379 -v /tmp/redis:/data:rw --name redis redis --save 60 1 --loglevel warning
