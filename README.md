# ARCG_CC

## セットアップ (uv)

```bash
cd ARCG_CC/curve_fitter
uv sync
uv run python main.py
```

## pip

```bash
pip install -r curve_fitter/requirements.txt
python curve_fitter/main.py
```

## DXF出力
保存形式で `dxf` を選択すると LINE/ARCエンティティの2D DXFを出力します。


## Related Projects 

- https://github.com/Yoshinobu-Ishizaki/arcg-wx2

    wxPythonを使用した類似のプログラム。アルゴリズムは全く異なる。端点から順にセグメントを増加させるコードになっている。