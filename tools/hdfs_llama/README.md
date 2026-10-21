# LogHub HDFS → Llama 3.1 분할 도구

`block_id` 단위의 사건 흐름을 보존하면서 HDFS 로그를 LLM 입력 크기에 맞춘다. 외부 Python 패키지는 필요 없다.

## 바로 실행

```bash
cd tools/hdfs_llama
python3 split_hdfs.py data/HDFS_2k.log -o output \
  --max-tokens 8192 --reserve-tokens 2048
```

생성물:

- `output/chunk_00001.txt`: Llama에 넣을 prompt-ready 로그 묶음
- `output/manifest.jsonl`: 파일별 block id, 추정 토큰, SHA-256
- `output/summary.json`: 분할 설정과 통계

구조화 CSV도 입력할 수 있다.

```bash
python3 split_hdfs.py data/HDFS_2k.log_structured.csv -o output_csv --format structured
```

## 크기 설정

Llama 3.1 자체는 긴 context를 지원하지만, 실행 엔진의 실제 `num_ctx`/메모리 설정이 더 작을 수 있다.
`--max-tokens`에는 실제 런타임 context 값을 넣는다. 기본 8,192 중 2,048토큰은 시스템 프롬프트와 답변용으로 남긴다.
로그는 ID와 기호가 많아 단어 기반 계산이 부정확하므로 기본값은 보수적인 `3 chars/token` 추정치다.

예: Ollama에서 `num_ctx=32768`로 실행한다면:

```bash
python3 split_hdfs.py HDFS.log -o output --max-tokens 32768 --reserve-tokens 4096
```

실제 tokenizer로 사전 검증할 수 있다면 `manifest.jsonl`의 추정치 대신 그 결과를 우선한다.

## 권장 분석 워크플로우

1. **분할:** 위 명령으로 raw/structured 로그를 block trace별로 묶는다.
2. **Map:** [prompts.md](prompts.md)의 1단계 프롬프트로 chunk를 하나씩 분석하고 응답을 JSONL로 저장한다.
3. **Reduce:** 2단계 프롬프트로 같은 block의 여러 part와 chunk 결과를 통합한다.
4. **평가:** 마지막에만 `anomaly_label.csv`를 block id로 결합해 precision/recall/F1과 오탐·미탐을 계산한다.
5. **회귀 테스트:** 모델/프롬프트/양자화 버전을 고정하고 같은 샘플로 반복 비교한다.

중요: `HDFS_2k.log`는 파이프라인 확인용 샘플이며, 공식 HDFS v1의 anomaly label 전체와 직접 대응하는 완전한 평가 세트로 간주하면 안 된다.

## 테스트

```bash
cd tools/hdfs_llama
python3 -m unittest -v test_split_hdfs.py
```
