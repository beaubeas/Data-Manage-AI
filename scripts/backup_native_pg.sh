databases=$(psql -h localhost -U ${USER} -t -c "SELECT datname FROM pg_database WHERE datname NOT IN ('template0', 'template1', 'postgres', 'monster_rag');" postgres)

# Loop through each database and dump only data
for db in $databases; do
    pg_dump \
      --host=localhost \
      --port=5432 \
      --username=${USER} \
      --dbname=$db \
      --encoding=UTF8 \
      --file="/tmp/${db}_data.sql"
    
    echo "Dumped data from $db"
done
