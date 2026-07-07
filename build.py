# -*- coding: utf-8 -*-
import re, json, sys, os

SRC = r"K:\2026年上海初中考纲词汇用法手册.txt"
TEMPLATE = r"I:\WorkBuddy\2026-07-07-09-29-05\template.html"
OUT = r"I:\WorkBuddy\2026-07-07-09-29-05\2026年上海初中考纲词汇用法手册.html"

# 词库 OCR 拼写校正（合并被空格拆分的词、修复数字代字母、处理撇号音标）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from correct import correct_line, is_valid

with open(SRC, encoding="utf-8") as f:
    lines = f.read().split("\n")

# 词条起始行：可选前缀(√◆→>) + 数字 + .或、 + 可选*★ + 单词(允许数字/./'/-) + 可选括号 + 其余
ENTRY_RE = re.compile(
    r'^\s*(?:[√◆→>])?\s*(\d+)\s*[\.、]\s*([*★]*)\s*([A-Za-z0-9][A-Za-z0-9\.\'\-]*)\s*(\([^)]*\))?\s*(.*)$'
)
def is_phonetic(s):
    """判断文本是否「像」教材音标：仅含字母、撇号、冒号、点、连字符，不含空格/中文/数字，长度 1-30。
       用于过滤被误当作音标的中文释义（如 /lots of/、/n.行动/）。"""
    if not s or ' ' in s or '\t' in s:
        return False
    if re.search(r'[一-鿿]', s) or re.search(r'[0-9]', s):
        return False
    if len(s) > 30:
        return False
    return bool(re.fullmatch(r"[A-Za-z'.:，·\-]+", s))

def extract_phon(rest):
    """从单词后的文本中提取音标，返回 (phonetic, after)。容错：
       /.../ 正常； '.../ 或 ’.../ 破损；否则取首个空白前内容。
       若捕获到的 /.../ 内容不像音标（含中文/空格/数字），则视为没有音标，
       整段文本保留为 after，避免中文释义被误当成音标。"""
    m = re.search(r'[/／]([^/／\n]*?)[/／]', rest)
    if m:
        phon = m.group(1).strip().strip('/／').strip()
        if is_phonetic(phon):
            return phon.replace(' ', ''), rest[m.end():]
        return '', rest  # 内容不像音标 -> 整段当释义
    m = re.search(r'[\'\u2019]([^/\n]*?)[/／]', rest)
    if m:
        phon = m.group(1).strip().strip('/／').strip()
        if is_phonetic(phon):
            return phon.replace(' ', ''), rest[m.end():]
        return '', rest
    sp = re.split(r'\s+', rest, maxsplit=1)
    if len(sp) > 1:
        ph = sp[0].lstrip('/／\'')
        ph2 = ph.strip().strip('/／').strip()
        if is_phonetic(ph2):
            return ph2.replace(' ', ''), sp[1]
        return '', rest  # 首个空白前不像音标 -> 整段当释义
    return '', rest
POS_RE = re.compile(
    r'^\s*(?:ad\s*v|vi\.?|vt\.?|aux|modal|abbr|n\.?|v\.?|adj\.?|adv\.?|prep\.?|conj\.?|pron\.?|num\.?|art\.?|int\.?)(?![A-Za-z])',
    re.I | re.ASCII
)
FORM_RE = re.compile(
    r"^([A-Za-z][A-Za-z' \-]*?)\s+(ad\s*v|vi\.?|vt\.?|aux|modal|abbr|n\.?|v\.?|adj\.?|adv\.?|prep\.?|conj\.?|pron\.?|num\.?|art\.?|int\.?)\.?\s*(.*)$",
    re.I
)
MARKERS = ['词形', '拓展', '词组', '反义', '近义', '名师', '谚语', '辨析', '用法', '注意', '联想', '记忆', '点拨', '例句', '考频', '助记', '中考', '提示', '考纲']

def has_cn(s): return bool(re.search(r'[一-鿿]', s))
def has_en(s): return bool(re.search(r'[A-Za-z]', s))
def has_both(s): return has_en(s) and has_cn(s)

def is_marker(s):
    for kw in MARKERS:
        if kw in s:
            return kw
    return None

def parse_pos_meaning(text):
    t = text.strip()
    # 去掉开头的括号注释，如（复abilities）
    t = re.sub(r'^[（(][^()（）]*[)）]\s*', '', t)
    m = POS_RE.match(t)
    if m:
        pos = m.group(0).strip()
        meaning = t[m.end():].strip()
        # 去掉词性前可能残留的斜杠（如 n/n.行动 -> n.行动）
        meaning = re.sub(r'^[/／\s]+', '', meaning)
        # 去掉与已捕获词性重复的起始词性标记（如 pos=n 且 meaning 以 "n." 开头）
        if meaning.lower().startswith(pos.lower() + '.'):
            meaning = meaning[len(pos) + 1:].lstrip('.')
        elif meaning.lower().startswith(pos.lower()):
            meaning = meaning[len(pos):].lstrip('.')
        return pos, meaning.strip()
    return None

def parse_form(s):
    m = FORM_RE.match(s.strip())
    if m:
        w = m.group(1).strip()
        p = m.group(2).strip().rstrip('.') + '.'
        mm = m.group(3).strip()
        return {'w': w, 'p': p, 'm': mm}
    return None

# 允许作为首片段的合法单字母词（其余单字母如 x/q 不会被 is_valid 放行）
ALLOW1 = {'a', 'i', 'o', 'I'}

def _seg_ok(p):
    return is_valid(p) and (len(p) >= 2 or p in ALLOW1)

def split_merged_headword(w):
    """对「非合法单词但可切分为合法词」的词头做安全切分（处理 afew -> a few、alot -> a lot 之类 OCR 粘连）。
       合法单词（is_valid 为真）不会被切分。仅当切分后每段都是合法词时才生效。"""
    if ' ' in w or len(w) > 14 or is_valid(w):
        return w
    def seg(s):
        if _seg_ok(s):
            return [s]
        if len(s) <= 1:
            return None
        for i in range(1, len(s)):
            if _seg_ok(s[:i]):
                rest = seg(s[i:])
                if rest:
                    return [s[:i]] + rest
        return None
    r = seg(w)
    if r and len(r) > 1 and all(_seg_ok(p) for p in r):
        return ' '.join(r)
    return w

# 常见词尾（即便单独看不是词，也视为合理后缀，避免误裁）
COMMON_SUFFIX = {'s','es','ed','ing','ly','er','est','ness','ment','tion','ation',
                 'able','ible','ful','less','ous','al','ic','ify','ize','ise','en',
                 'y','ist','ism','ship','hood','ward','wise','fold','teen','ty','th'}

def trim_trailing_garbage(w):
    """裁掉词尾的 OCR 垃圾后缀：如 actionakf -> action。
       仅在整体非法、长度>4、且存在>=3字母的合法前缀、剩余后缀为短促乱码时使用。"""
    if is_valid(w) or len(w) <= 4 or ' ' in w:
        return w
    for i in range(len(w) - 1, 2, -1):
        if is_valid(w[:i]):
            suffix = w[i:]
            if 2 <= len(suffix) <= 4 and not is_valid(suffix) and suffix not in COMMON_SUFFIX:
                return w[:i]
    return w

# 切分词条
entries = []
cur = None
for ln in lines:
    cln = correct_line(ln)            # 先校正 OCR 拼写（合并拆分词、修数字）
    m = ENTRY_RE.match(cln)
    if m:
        if cur is not None:
            entries.append(cur)
        word = m.group(3).strip()
        rest = m.group(5)
        # 撇号代替斜杠的音标：adult'adalt -> adult (/adalt/)
        if "'" in word:
            i = word.index("'")
            head, tail = word[:i], word[i+1:]
            if re.match(r'^[a-z]{2,12}$', tail) and is_valid(head):
                word = head
                rest = '/' + tail + rest
        phon, after = extract_phon(rest)
        word = trim_trailing_garbage(split_merged_headword(word))
        # 过滤垃圾行：音标须像音标；或至少有词性标注；或含有中文释义（如 "1.afew有些；几个"）
        real = (bool(phon) and bool(re.search(r'[A-Za-z]', phon))) \
               or bool(POS_RE.match(after.strip())) \
               or has_cn(after)
        cur = {
            'idx': int(m.group(1)),
            'star': m.group(2),
            'word': word,
            'ph': ('/' + phon + '/') if phon else '',
            'after': after,
            'real': real,
            'lines': []
        }
    else:
        if cur is not None:
            cur['lines'].append(ln)

if cur is not None:
    entries.append(cur)

raw = []
for e in entries:
    if not e['real']:
        continue
    word = e['word']
    after = e['after']
    ph = e['ph']
    segs = []
    ex = []
    forms = []
    phr = []
    notes = []
    last_form = None
    section = 'meaning'

    # 头部释义
    pm = parse_pos_meaning(after)
    if pm:
        segs.append({'pos': pm[0], 'm': pm[1]})

    for ln in e['lines']:
        s = ln.strip()
        if not s:
            continue
        mk = is_marker(s)
        if mk in ('词形', '拓展'):
            section = 'forms'
            continue
        if mk == '词组':
            section = 'phr'
            continue
        if mk:
            # 其它标记行（反义/近义/名师/谚语…）本身作为补充说明
            section = 'note'
            notes.append(s)
            continue
        # 非标记行，按当前段落处理
        if section == 'forms':
            f = parse_form(s)
            if f:
                forms.append(f)
                last_form = f
                continue
            if last_form and has_cn(s) and not has_en(s):
                last_form['m'] = (last_form['m'] + ' ' + s).strip()
                continue
            continue
        if section == 'phr':
            if s:
                phr.append(s)
            continue
        # 先判定词性释义行，再判定例句（避免 "v.承认" 被 has_both 误判为例句）
        pm2 = parse_pos_meaning(s)
        if pm2:
            segs.append({'pos': pm2[0], 'm': pm2[1]})
            continue
        if has_both(s):
            ex.append(s)
            continue
        if s:
            notes.append(s)

    if not segs:
        # 兜底：从被误并入音标/头部的内容中找回中文释义（覆盖 according to 等短语词条）
        cjk = re.findall(r'[一-鿿]+', after + ' ' + ph)
        if cjk:
            segs.append({'pos': '', 'm': '；'.join(cjk)})
        else:
            segs.append({'pos': '', 'm': ''})

    allm = '；'.join(s['m'] for s in segs if s['m'])
    toks = []
    seen = set()
    for s in segs:
        for t in re.split(r'[，,；;、]', s['m']):
            t = t.strip()
            if t and t not in seen:
                seen.add(t)
                toks.append(t)

    raw.append({
        'i': e['idx'],
        'w': word,
        'ph': e['ph'],
        'pos': segs[0]['pos'],
        'segs': segs,
        'ex': ex,
        'forms': forms,
        'phr': phr,
        'notes': notes,
        'allm': allm,
        'toks': toks,
    })

# 去重：同一单词在原文中可能重复出现（全书多遍），保留内容最丰富的一份
def richness(d):
    return len(d['forms']) + len(d['ex']) + len(d['segs']) + (1 if d['ph'] else 0) + len(d['toks'])

best = {}
for d in raw:
    k = d['w'].lower()
    if k not in best or richness(d) > richness(best[k]):
        best[k] = d
data = list(best.values())
data.sort(key=lambda x: x['i'])

# ---------- 美式标准音标校正 ----------
# 使用 open-dict-data/ipa-dict 的 en_US 数据集（标准美式 IPA），
# 将每个单词的音标替换为 /.../ 形式的美式国际音标；多词短语与未收录词保留原音标。
IPA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ipa_en_US.txt")
def load_american_ipa(path):
    m = {}
    if not os.path.exists(path):
        print("WARNING: 未找到美式音标数据 %s，跳过音标校正" % path)
        return m
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.rstrip("\n")
            if not ln:
                continue
            w, _, ipa = ln.partition("\t")
            ipa = ipa.strip().strip("/").strip()
            # 仅接受不含中文、长度合理的合法音标串
            if ipa and 1 <= len(ipa) <= 40 and not re.search(r'[一-鿿]', ipa):
                m[w.lower()] = ipa
    return m

AM_IPA = load_american_ipa(IPA_PATH)
UK_IPA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ipa_en_GB.txt")
def load_british_ipa(path):
    m = {}
    if not os.path.exists(path):
        print("WARNING: 未找到英式音标数据 %s，跳过英式音标" % path)
        return m
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.rstrip("\n")
            if not ln:
                continue
            w, _, ipa = ln.partition("\t")
            ipa = ipa.strip().strip("/").strip()
            if ipa and 1 <= len(ipa) <= 40 and not re.search(r'[一-鿿]', ipa):
                m[w.lower()] = ipa
    return m
UK_IPA = load_british_ipa(UK_IPA_PATH)
def uk_for(w):
    low = w.lower()
    if low in UK_IPA:
        return UK_IPA[low]
    for v in am_variants(w):
        if v in UK_IPA:
            return UK_IPA[v]
    return None
# 英式拼写 -> 美式拼写候选（仅做安全的后缀映射，避免误改）
_OUR_KEEP = {'your','four','pour','sour','tour','hour','flour','mourn','court','course','lour','dour','devour','glamour'}
def am_variants(w):
    low = w.lower(); c = []
    if low.endswith('ise'): c.append(low[:-3] + 'ize')
    if low.endswith('yse'): c.append(low[:-3] + 'yze')
    if low.endswith('our') and low not in _OUR_KEEP:
        c.append(low[:-3] + 'or')
    return c
ipa_hit = 0
for d in data:
    w = d['w']
    if ' ' in w or '...' in w:
        continue  # 多词短语/语法结构/含省略号：保留原（教材）音标
    am = AM_IPA.get(w.lower())
    if not am:
        for v in am_variants(w):
            if v in AM_IPA:
                am = AM_IPA[v]; break
    if am:
        d['ph'] = '/' + am + '/'
        ipa_hit += 1
    uk = uk_for(w)
    if uk:
        d['ph_uk'] = '/' + uk + '/'
single = sum(1 for d in data if ' ' not in d['w'])
print(f"美式标准音标覆盖: {ipa_hit}/{single} 个单词（未覆盖的保留原教材音标）")
print(f"含音标的词条: {sum(1 for d in data if d['ph'])}")

with_forms = sum(1 for d in data if d['forms'])
with_multi = sum(1 for d in data if len(d['toks']) > 1)
empty_mean = sum(1 for d in data if not d['toks'])
print(f"词条总数: {len(data)}")
print(f"有声标: {sum(1 for d in data if d['ph'])}")
print(f"有词形变化: {with_forms}")
print(f"多释义词条: {with_multi}")
print(f"空释义词条: {empty_mean}")

# 校验前几个
for d in data[:3]:
    print("---")
    print(d['w'], d['ph'], d['pos'], "| toks:", d['toks'], "| forms:", [(f['w'], f['p']) for f in d['forms']])

# 读取模板并注入
with open(TEMPLATE, encoding="utf-8") as f:
    tpl = f.read()

jstr = json.dumps(data, ensure_ascii=False)
jstr = jstr.replace('</', '<\\/')  # 防止 </script> 提前闭合

if '__VOCAB_DATA__' not in tpl:
    print("ERROR: 模板中未找到占位符 __VOCAB_DATA__")
    sys.exit(1)

html = tpl.replace('__VOCAB_DATA__', jstr)
with open(OUT, 'w', encoding="utf-8") as f:
    f.write(html)

print("已生成:", OUT)
print("文件大小(字节):", len(html.encode('utf-8')))

# ---- 诊断：查看若干空释义词条，判断是否为解析问题 ----
empty = [d for d in data if not d['toks']]
print("\n=== 空释义词条示例(前8) ===")
for d in empty[:8]:
    print(f"  [{d['w']}] ph={d['ph']} segs={d['segs']} ex={d['ex'][:1]} notes={d['notes'][:1]}")

# ---- 诊断 ----
from collections import Counter
wc = Counter(d['w'] for d in data)
dups = {w: c for w, c in wc.items() if c > 1}
print("重复单词:", dups)
print("前5词条 idx/word:", [(d['i'], d['w']) for d in data[:5]])

# 查找 ENTRY_RE 漏掉的近似条目行
relaxed = re.compile(r'^\s*(?:[√◆→>])?\s*\d+\s*[\.、]\s*\*?[*★]?\s*[A-Za-z]')
missed = [ln for ln in lines if relaxed.match(ln) and not ENTRY_RE.match(ln)]
print("ENTRY_RE 漏匹配行数:", len(missed))
for ln in missed[:20]:
    print("  MISS:", ln[:80])
