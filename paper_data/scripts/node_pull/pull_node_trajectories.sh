#!/bin/bash
# pull.sh <label> <job> <b64spec>  -- run si2ca_extract.py on one node, save <label>.jsonl.gz
SP=/path/to/scratchpad
mkdir -p $SP/pull
cd ~/xiao/projects/slime
label=$1 job=$2 spec=$3
B64PY=$(base64 -w0 $SP/si2ca_extract.py)
for try in 1 2 3; do
  timeout 1500 env -u LD_LIBRARY_PATH bash configs/ssh_node.sh $job 0 "echo $B64PY | base64 -d | python3 - $spec" \
    > $SP/pull/raw_$label.txt 2> $SP/pull/err_$label.txt
  if grep -q '^XENDX$' $SP/pull/raw_$label.txt; then
    sed -n '/^XSTARTX$/,/^XENDX$/p' $SP/pull/raw_$label.txt | sed '1d;$d' | base64 -d > $SP/pull/$label.jsonl.gz \
      && gzip -t $SP/pull/$label.jsonl.gz \
      && { echo "$label ok $(stat -c %s $SP/pull/$label.jsonl.gz) bytes (try $try)"; rm -f $SP/pull/raw_$label.txt; exit 0; }
  fi
  sleep 30
done
echo "$label FAIL"; tail -3 $SP/pull/err_$label.txt
