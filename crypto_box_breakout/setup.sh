#!/usr/bin/env bash
# 노트북 터미널 원클릭 셋업: 가상환경 생성 + 의존성 설치 + 동작 확인.
#   bash setup.sh
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
echo "[1/4] 가상환경(.venv) 생성"
$PY -m venv .venv

echo "[2/4] 의존성 설치"
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "[3/4] 테스트"
python tests/test_strategy.py

echo "[4/4] 오프라인 데모(합성데이터)"
python run_backtest.py --demo | tail -20

cat <<'EOF'

✅ 셋업 완료. 다음:
  source .venv/bin/activate
  python fetch_data.py                     # BTC/ETH 실데이터 다운로드(인터넷 필요)
  python run_backtest.py --csv data/btc_1h.csv
  python analyze.py data/btc_1h.csv        # 견고성 검증
EOF
