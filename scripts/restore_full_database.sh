dump_dir="/tmp/"

for dump in ${dump_dir}/*_data.sql; do
    db=$(basename $dump _data.sql)  # Remove _data.sql to get database name
    psql \
      --host=localhost \
      --port=5432 \
      --username=${USER} \
      -d postgres \
      -c "CREATE DATABASE $db;"
      
    psql \
      --host=localhost \
      --port=5432 \
      --username=${USER} \
      --dbname=$db \
      --file=$dump
    
    echo "Restored data to $db"
done
