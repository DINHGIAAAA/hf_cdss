import argparse
import json
import traceback
from pathlib import Path
from kafka import KafkaProducer
from kafka.errors import KafkaError

def main() -> None:
    parser = argparse.ArgumentParser(description="Publish JSONL file records to a Kafka topic.")
    parser.add_argument("--input-file", required=True, help="Path to the input .jsonl file")
    parser.add_argument("--topic", default="important_sections", help="Kafka topic to publish messages to")
    parser.add_argument("--kafka-bootstrap-servers", default="localhost:9092", help="Kafka bootstrap servers")
    args = parser.parse_args()

    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"Error: File '{args.input_file}' not found.")
        return

    # 1. Khởi tạo Kafka Producer
    print(f"Connecting to Kafka at {args.kafka_bootstrap_servers}...")
    try:
        producer = KafkaProducer(
            bootstrap_servers=args.kafka_bootstrap_servers,
            # Tự động chuyển đổi Python Dictionary thành JSON bytes trước khi gửi
            value_serializer=lambda m: json.dumps(m, ensure_ascii=False).encode('utf-8')
        )
    except KafkaError as e:
        print(f"FATAL: Could not connect to Kafka. Details: {e}")
        return

    # 2. Đọc file JSONL và đẩy dữ liệu
    print(f"Reading from '{args.input_file}' and publishing to topic '{args.topic}'...")
    count = 0
    
    with input_path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            try:
                # Chuyển dòng text thành dictionary
                record = json.loads(line)
                
                # Đẩy vào Kafka topic (bất đồng bộ)
                producer.send(args.topic, value=record)
                count += 1
                
                if count % 100 == 0:
                    print(f"  ...Published {count} messages...")
            except json.JSONDecodeError as e:
                print(f"WARNING: Skipping invalid JSON line. Error: {e}")
            except Exception as e:
                print(f"\n[ERROR] Lỗi không xác định khi publish dòng vào Kafka. Error: {e}")
                traceback.print_exc()

    # 3. Đảm bảo tất cả message trong buffer được gửi đi trước khi đóng kết nối
    producer.flush()
    producer.close()
    print(f"\nDone! Successfully published {count} messages to topic '{args.topic}'.")

if __name__ == "__main__":
    main()