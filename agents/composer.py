"""② 整形AI（マルチモーダル）：transcript＋画像＋参考情報＋プロンプト設定 → 構造化記録。

プロンプトは「固定フレーム」（読者の定義・事実の扱い・組み立て手順・書式・画像の仕組み＝コード固定）と
「編集スロット」（title/summary/details/properties/style＝プロンプト設定ページで編集可）で構成する。
FIXED_DISPLAY はプロンプト設定ページの「🔒 固定ルール」表示に使う。

- 出力は FormatOutput（structured output）。AIはmarkdownを書かず型の穴埋めのみ
- 画像への言及・配置（Bullet.images）・キャプション（desc）も一体で生成
- 画像にAIは手を入れない（マークはユーザーのクリック。描画はプログラム）

refine_structured：④ 修正AI。検証AIが検出した「事実の改変」の該当箇所だけを直す。
revise_structured：ユーザーの修正指示。指示の箇所だけ変更（他は一字一句維持）。
"""
import re

from google import genai
from google.genai import types

from core import usage
from core.schema import FormatOutput

_IMG_REF = re.compile(r"画像\s*(\d+)")  # 本文中の「画像4」「画像4 A」等の言及を拾う


def autoplace_images(out: FormatOutput, n_images: int) -> FormatOutput:
    """本文で言及されている画像を、未配置なら該当セクションの親bulletのimagesに補う（保険）。

    imagesフィールドは親bulletにしか無いため、子・孫の深い階層で言及された画像を
    AIが親へ引き上げ損ねると「その他の画像」に落ちる。ここで機械的に補完する。
    - 走査対象は details のみ（inline画像はdetailsにしか出ない）
    - 既に配置済みの番号は動かさない。first-mention-wins（先に出た親に付ける）で重複配置しない
    """
    placed = {n for sec in out.details for b in sec.bullets for n in b.images}
    for sec in out.details:
        for b in sec.bullets:
            texts = [b.text]  # この親のサブツリー全体（親→子→孫）のテキストを集める
            for s in b.sub:
                texts.append(s.text)
                texts.extend(s.sub)
            refs = {int(m.group(1)) for t in texts for m in _IMG_REF.finditer(t or "")}
            for n in sorted(refs):
                if 1 <= n <= n_images and n not in placed:
                    b.images.append(n)
                    placed.add(n)
    return out

MODEL = "gemini-2.5-flash"

FIXED_CORE = """あなたは、現場で口頭報告された内容を「あとから読んで使える記録」に整える専門家です。

【読者とゴール】
読者は「数ヶ月後の本人」と「その場にいなかった同僚」。読み手が短時間で
①なぜやったか（きっかけ・目的） ②何をしたか（概要と、日時・場所・人・対象・方法など）
③何が分かったか（事実） ④何をどう判断したか・なぜか ⑤次に何をするか
を把握できる記録を作る。

【事実の扱い（他のすべてに優先）】
- ソース（文字起こし・画像・補足テキスト・作業日）に無いことを書かない
- 数値・単位・固有名詞・サンプルID・合否・状態はソースのまま使う
- 聞き取れない・不明な箇所は「[不明]」のまま残す
- 事実と推測・解釈は、語尾や表現で区別が伝わるように書く（以下は例であり、この形に限らない）：
  - 事実の例：「〜であった」「〜が確認された」「〜と確認」「〜が通過した」
  - 推測・解釈の例：「〜の可能性が高い」「〜と思われる」「〜と考えられる」
- 確度を保存する：話者が断定したことは断定形のまま、推測として述べたことは推測形のまま書く

【組み立ての手順（この順で考える）】
1. 文字起こし全体を読み、次を特定する：
   (a) きっかけと目的
   (b) 何をしたか——まず概要（「〜を測定した」「〜の落下試験を実施した」など）。
       あわせて、発話に散らばる日時・場所・メンバー・対象・機器・手法・手順なども拾い集める
   (c) 分かった事実  (d) 判断とその理由  (e) 次にやること
2. 各情報を、セクション定義に従って最も適切な1箇所だけに置く（同じ内容を2箇所に書かない）
3. セクションの中は、時系列の羅列ではなく話題ごとのツリーで組む：
   - 親（text）＝話題・主張（例「内部部品の破損の可能性」「修理費用」「△△の測定結果」）
   - 子（sub の text）＝その話題の事実・根拠・分析（事実→解釈の順に並べる）
   - 孫（sub の中の sub）＝さらに詳しい観察・数値
   - 1つの親の子は2〜4個を目安にする。5個を超えるなら話題を分けて親を増やす
   - 誰の発言・観察かは語尾や文中で示す（「〜との説明」「〜との指摘」「◯◯が確認」）。
     発言者名を親（見出し）にしない
   - 同種のものの列挙（サンプル別・条件別・手順の順番）は並列に並べてよい
4. 発話で言及した各画像の番号を、それに言及した箇条書きの images に入れる（詳細は【画像の扱い】）

【ツリーの形（例）】
悪い形（1つの親に子が大量にぶら下がる壁。話者の推測が断定になっている）：
- ◯◯からの説明
    - 部品が破損している
    - 原因は埃の詰まり
    - 水の出方が異常だった
    - 現状の使用は可能
    - 費用は約3万円
    - 寿命は約7年
    - モーター音も大きい
良い形（話題ごとに親を分ける・子は2〜4個。帰属は語尾で。事実→解釈の順。話者の確度を保存）：
- 内部の部品が破損している可能性が高い、との説明
    - 水の出方が異常であった（上は正常・下は逆方向）　←この行が画像3の内容なら、この親の images に 3 を入れる
    - 内部から大量の埃が確認された
    - 埃が水路を妨げて部品が破損したと考えられる、とのこと
- 現状の使用は可能と思われる、との説明
- 修理する場合の費用は約3万円、との説明"""

FIXED_FORMAT = """【書式（機械的制約）】
- text は素の文。行頭記号や「理由：」「目的：」等のラベル接頭辞を付けない（「日時：」等のメタ情報の列挙は除く）
- 1項目1内容。ネストは最大3階層
- 該当の無いセクションは出力しない"""

FIXED_IMAGES = """【画像の扱い】
- 画像は「画像1」「画像2」…と番号で扱う。発話中の「1枚目」「5枚目の画像」等は対応する画像番号に読み替える
- 本文で画像に言及するときは「画像1」「画像1のA」のように書く
- 配置：その画像に言及しているセクション内の箇条書きの images に画像番号を入れる
  （そのセクションの末尾に表示される）。複数セクションで言及される場合は最初のセクションに入れる。
  どのセクションでも言及されない画像はどの images にも入れない（自動で「その他の画像」に配置される）。
  同じ画像番号を複数の箇条書きに入れない
- captions：全ての画像について desc（説明文のみ）を返す。音声・補足テキストでの説明を使い、
  言及の無い画像は空文字にする（書式・番号・ファイル名はプログラムが付与する）
- マークがある画像は、各マーク（A, B…）が何を指すかを desc に含める
- 画像の内容はソースとして使ってよいが、画像から断定できないことは書かない

【補足テキストの扱い】（ある場合）
- ユーザーが貼り付けた補足テキスト（URL・参考情報など）もソースの一部
- 音声で説明があれば関連セクションの箇条書きに記載する（URL・文字列は一字一句そのまま）
- 説明の無いものは「その他の情報・Tips」に記載する"""

FIXED_CHECK = """【出力前のセルフチェック】
1. 発話で言及した各画像が、いずれかの箇条書きの images に入っているか
2. サマリに「下した結論・判断（どうすることにしたか）」が1項目あるか
3. ネクストアクションがある場合、サマリの最後の項目が「ネクストアクション」（内容は sub）になっているか（無い記録では、サマリ・詳細ともこの項目自体を書かない）
4. 1つの親の子が5個を超えていないか（超えるなら話題を分けて親を増やす）
5. 同じ内容を2つのセクションに書いていないか（サマリは詳細の要約なので除く）
6. 話者が推測として述べたことが断定になっていないか"""

# プロンプト設定ページの「🔒 固定ルール（変更不可）」表示用
FIXED_DISPLAY = FIXED_CORE + "\n\n" + FIXED_FORMAT + "\n\n" + FIXED_IMAGES + "\n\n" + FIXED_CHECK

PROMPT_TMPL = FIXED_CORE + """

【出力フィールド】
- title：{title}
- one_liner：この記録が何かを1行で
- summary：heading を空文字にした1つのセクションに bullets として入れる。方針：
{summary}
- details：以下の見出し定義に従う
{details}
- 各箇条書き（Bullet）は text／sub（子。各子は text と孫 sub を持つ）／images（この項目が言及する画像番号）を持つ
- captions：全画像の説明（詳細は【画像の扱い】）
- did / result：{properties}

【文体・追加ルール】（固定ルールと矛盾する場合は固定ルールを優先する）
{style}

""" + FIXED_FORMAT + "\n\n" + FIXED_IMAGES + """

【作業日】{work_date}（ユーザーがUIで指定した値。音声に無い日付を推測で補わない）
{extra}{ref}
文字起こし（記録のソース）：
---
{transcript}
---
この後に各画像（画像1, 画像2, …の順）とそのメタ情報が続きます。

""" + FIXED_CHECK + "\n"

REFINE_TMPL = """前回の記録に「事実の改変」が見つかりました。指摘された箇所だけを、文字起こし（ソース）に忠実に直してください。

【最重要】指摘された箇所【以外】は一字一句変更しないこと。
- セクション構成・見出し・他の箇条書き・images・captions はそのまま維持する
- 直すのは指摘された事実部分だけ。新たな要約・追記・整え直しはしない
- 指摘の場所が「プロパティ」の場合は、JSONの did / result フィールドを指す。
  タイトル・これなに？・サマリ（summary）への指摘も同様に該当フィールドを直す

文字起こし（ソース）：
---
{transcript}
---

前回の記録（このJSONをベースに、指摘箇所だけ直して同じ構造で返す）：
{current}

直すべき事実の改変（この箇所だけ修正）：
{issues}
"""

REVISE_TMPL = """ユーザーから、この記録への修正指示があります。指示された変更【だけ】を適用してください。

【最重要】指示に関係しない箇所は一字一句変更しないこと。
- セクション構成・見出し・他の箇条書き・images・captions はそのまま維持する
- 新たな要約・追記・整え直しはしない。事実を変えない・推測で補完しないも維持する

文字起こし（ソース）：
---
{transcript}
---

現在の記録（このJSONをベースに、指示の箇所だけ変えて同じ構造で返す）：
{current}

修正指示：
{instruction}
"""


def _image_parts(images: list) -> list:
    """画像メタ文字列と画像パーツを交互に並べる（どれが画像Nかを明示）"""
    parts = []
    for im in images:
        meta = f"画像{im['n']}（ファイル名: {im['filename']}）"
        if im.get("marks"):
            meta += " マーク: " + ", ".join(
                f"{m['label']}（{m.get('tool', '丸')}・{m.get('cname', '赤')}, x={m['x']}, y={m['y']}）"
                for m in im["marks"]
            )
        else:
            meta += " マークなし"
        parts.append(meta)
        parts.append(types.Part.from_bytes(data=im["bytes"], mime_type=im.get("mime", "image/png")))
    return parts


def compose_record(transcript: str, images: list, templates: dict,
                   work_date=None, extra_instruction: str = "", ref_text: str = "") -> FormatOutput:
    """構造化記録を生成。images: [{n, filename, bytes, mime, marks:[{label,tool,cname,x,y}]}]"""
    extra = ""
    if extra_instruction.strip():
        extra = f"\n【ユーザーからの追加指示（固定ルールの範囲で優先して反映）】\n{extra_instruction.strip()}\n"
    ref = ""
    if (ref_text or "").strip():
        ref = f"\n補足テキスト（ユーザー貼り付け・ソースの一部）：\n---\n{ref_text.strip()}\n---\n"
    prompt = PROMPT_TMPL.format(
        title=templates["title"], summary=templates["summary"],
        details=templates["details"], properties=templates["properties"],
        style=templates["style"],
        work_date=work_date or "（不明）", extra=extra, ref=ref, transcript=transcript,
    )
    client = genai.Client()
    resp = client.models.generate_content(
        model=MODEL,
        contents=[prompt] + _image_parts(images),
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=FormatOutput,
        ),
    )
    usage.record(MODEL, resp, "②整形")
    return autoplace_images(resp.parsed, len(images))  # 言及済み画像の配置漏れを機械的に補完


def revise_structured(transcript: str, current: FormatOutput, instruction: str) -> FormatOutput:
    """修正指示：指示された箇所だけ変更（他は一字一句維持）。"""
    prompt = REVISE_TMPL.format(
        transcript=transcript,
        current=current.model_dump_json(),
        instruction=instruction.strip(),
    )
    client = genai.Client()
    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=FormatOutput,
        ),
    )
    usage.record(MODEL, resp, "②部分修正")
    return resp.parsed


def refine_structured(transcript: str, current: FormatOutput, issues) -> FormatOutput:
    """④ 修正AI：事実の改変の該当箇所のみ修正（他は不変）。"""
    issues_text = "\n".join(
        f"- [{getattr(i, 'section', '') or '場所不明'}] "
        f"元:「{i.source_says}」→ 記録:「{i.draft_says}」（{i.note}）" for i in issues
    )
    prompt = REFINE_TMPL.format(
        transcript=transcript,
        current=current.model_dump_json(),
        issues=issues_text,
    )
    client = genai.Client()
    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=FormatOutput,
        ),
    )
    usage.record(MODEL, resp, "④修正")
    return resp.parsed
