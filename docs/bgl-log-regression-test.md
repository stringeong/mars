# BGL 로그 회귀 시험 도구 사용법

## 1. 로그 분할

LogHub에서 받은 `BGL_2k.log`를 100줄씩 나눈다.

```bash
python scripts/split_log_chunks.py \
  benchmark/BGL_2k.log \
  benchmark/chunks
```

다음 파일이 생성된다.

```text
benchmark/chunks/
  BGL_2k.part_001.log
  BGL_2k.part_002.log
  ...
  BGL_2k.part_020.log
  BGL_2k.manifest.json
```

원본이 2,000줄이면 100줄짜리 파일 20개가 생성된다. Manifest에는 각 파일이
원본의 몇 번째 줄부터 몇 번째 줄까지 포함하는지가 기록된다.

기존 결과를 교체하려면 `--overwrite`를 추가한다.

## 2. 모델 출력 형식

각 로그 조각의 모든 줄을 순서대로 판정하고, 같은 이름의 JSON 파일로 저장한다.

```text
입력:  BGL_2k.part_001.log
출력:  BGL_2k.part_001.json
```

JSON에는 로그 줄과 같은 순서로 100개의 불리언 값을 넣는다. 경보 로그는 `true`,
정상 로그는 `false`다.

```json
{
  "predictions": [false, false, true, false]
}
```

배열만 저장해도 된다.

```json
[false, false, true, false]
```

모델에 다음 출력 지시를 사용할 수 있다.

```text
각 로그 줄을 독립적으로 판정하라. 운영상 경보나 이상을 나타내면 true, 정상 상태면
false로 판정한다. 입력 순서를 유지한 불리언 배열을 predictions 필드에 넣어 유효한
JSON 하나만 출력하라. 설명문과 마크다운은 출력하지 마라.
```

## 3. 채점

모델 출력 JSON을 하나의 폴더에 모은 뒤 LogHub의
`BGL_2k.log_structured.csv`와 비교한다.

```bash
python scripts/grade_bgl_predictions.py \
  benchmark/BGL_2k.log_structured.csv \
  benchmark/chunks/BGL_2k.manifest.json \
  benchmark/predictions \
  benchmark/scores
```

채점 결과는 다음 두 파일로 저장된다.

- `summary.json`: 정확도, TP, TN, FP, FN, 정밀도, 재현율, F1
- `details.csv`: 원본 줄별 정답, 모델 판정, T/F 결과와 오류

정확도가 기준보다 낮을 때 실패 상태로 종료하려면 `--fail-below`를 사용한다.

```bash
python scripts/grade_bgl_predictions.py \
  benchmark/BGL_2k.log_structured.csv \
  benchmark/chunks/BGL_2k.manifest.json \
  benchmark/predictions \
  benchmark/scores \
  --fail-below 0.95
```

## 4. 판정 기준

구조화 CSV의 `Label`이 `-`이면 정상(`false`), 다른 값이면 경보(`true`)로
판정한다. 로그 내용에 `error`라는 단어가 있더라도 `Label`이 `-`이면 정답은
정상이다.
