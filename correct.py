# -*- coding: utf-8 -*-
"""词库 OCR 拼写校正。
问题类型：
  1) 单词被空格拆开：capt a in -> captain；applicatio n -> application；ra n -> ran
  2) 数字代字母：ballo0n -> balloon；0ctober -> October
  3) 撇号代替斜杠的头词：adult'adalt -> adult (/adalt/)
策略：
  - 对每行做「最长合法前缀」贪心合并，但仅在满足以下之一时才合并：
      * 片段中存在「断裂音节」(长度<=2 且非常用短词，如 n/io/ra/ti/so)
      * 合并后整体是高频单词 (zipf >= 4.5)
    并对「首片段为常用词」的情况加保护，避免 As+an -> Asan 之类误合并。
  - 粘连单词(无空格)用词典做最长词贪心切分作为安全网。
  - 音标 /.../ 区域先遮罩，避免被当成英文校正。
"""
import re
from spellchecker import SpellChecker

sp = SpellChecker()
_wcache = {}

# 专有名词 / 缩写 / 缩写词（词典未必收录，但应视为正确）
EXTRA = set('''hainan beijing shanghai china chinese english american british canadian japanese
australian french german russian indian korean celsius fahrenheit tom mary john li wang zhang liu lily lucy jack tim sue
jim joe sam bob alice emma peter david mike tony helen hongkong taiwan xiamen guangzhou shenzhen
hangzhou nanjing tianjin wuhan chengdu kunming guilin sanya macao monday tuesday wednesday thursday
friday saturday sunday january february march april may june july august september october november
december spring summer autumn winter won't don't can't cannot it's i'll you'd he's she's they're we're
i'm you're that's isn't aren't didn't doesn't wouldn't shouldn't couldn't i've you've we've they've
let's there's what's who's hadn't wasn't weren't hasn't haven't ain't o'clock y'all mr mrs ms dr
prof esp etc aka ad vs pm am bc cd uk usa un wto who email a m p me m op
analyse analyze analyse programme program colour color centre center cafe kilometre kilometer
humour humor honour honor metre meter favour favor favourite favorite behaviour behavior
neighbour neighbor neighbourhood neighborhood odour odor flavour flavor labour labor office officer
lesson attention floor ocean entertain colourful colorful playful theatre theater
practise practice licence license defence defense'''.split())

# 数字/乱码直接映射（fix_digit 无法修复的形态，如 l 被识别成 0）
MANUAL_FIX = {'fo0or':'floor', '0cea':'ocean', '0cean':'ocean',
              'oficer':'officer', 'entert':'entertain', 'forestfprist':'forest'}

# 常用 <=2 字母真词：用于「断裂音节」判定（这些不算断裂片段）
REAL_SHORT = set('''a i o an as at be by do go he hi if in is it me my no of on or ox pa so to up us we ye
am ah ax ay ad ex ok lo ma uh um yo ya bo jo mo nu oh ow pi re sh ta un ut wo xi xu yu za zo
ab ac ag ai al ar aw ay bi ci da de di ed el em en er es et fa fe gi ha ho id ka ki la li mi mu
na ne ni od oe oi om op os pe po ra ri ro sa se si ti ug ur va vi vo wa wi ye'''.split())

def is_valid(w):
    w = w.lower()
    if not w or len(w) > 28:
        return False
    if w in EXTRA:
        return True
    if w in _wcache:
        return _wcache[w]
    ok = bool(sp.known([w]))
    _wcache[w] = ok
    return ok

def is_broken(frag):
    return len(frag) <= 2 and frag.lower() not in REAL_SHORT

# 词频（用于区分「应合并的单字」与「应保留的两词」）
try:
    from wordfreq import zipf_frequency as _zipf
    def freq(w):
        return _zipf(w.lower(), 'en')
except Exception:
    def freq(w):
        return 0.0

# 常被 OCR 拆开的合成词/复合词（首片段恰好是合法词，普通规则难以判定，显式兜底）
MERGE_FORCE = {'something','everything','anything','nothing','somebody','anybody','nobody',
               'without','within','into','although','already','together','weekend','homework',
               'everyone','anyone','everybody','classroom','bedroom','notebook','playground',
               'baseball','football','careful','useful','hopeful','helpful','peaceful',
               'sunflower','rainbow','cupboard','keyboard','spaceship','fireman','postman',
               'blackboard','whiteboard','greenhouse','somewhere','anywhere','nowhere',
               'breakfast','afternoon','birthday','grandmother','grandfather','schoolbag',
               'handwriting','headmaster','housework','neighbourhood'}

def should_merge(joined, frags):
    if not is_valid(joined):
        return False
    if joined in MERGE_FORCE:
        return True
    # 任一片段“断裂”(短且非真词，如 n/io/ra/ti/na/lyse/co/lour) -> 几乎肯定是 OCR 拆词
    if any(is_broken(f) for f in frags):
        return True
    # 拼接词频 >= 首片段词频（且本身算常见词）：覆盖 captain/celsius/baseball 之类
    # 头词比合成词更常见的（some>something、with>without）不会误合并，仍保留为两词
    if freq(joined) >= 1.0 and freq(joined) >= freq(frags[0]):
        return True
    return False

# OCR 数字 -> 字母 候选
DIGIT_MAP = {'0':['o'], '1':['l','i'], '2':['z'], '3':['e'], '4':['a'],
             '5':['s'], '6':['b'], '7':['t'], '8':['b','g'], '9':['g']}

PROPER = set('''monday tuesday wednesday thursday friday saturday sunday january february march
april may june july august september october november december chinese english american british
canadian japanese australian french german russian indian korean'''.split())

def fix_digit_token(tok):
    if not re.search(r'[0-9]', tok):
        return tok
    if tok.isdigit():                      # 纯数字（页码、序号 2）240 等）不动
        return tok
    if re.match(r'^[A-Za-z]\d+$', tok):    # 单元/编号代码 G6 U1 G634 等不动
        return tok
    if re.search(r'\d+(st|nd|rd|th)$', tok.lower()):  # 序数词 7th 不动
        return tok
    digits = [(i, c) for i, c in enumerate(tok) if c.isdigit()]
    # 优先「数字替换」候选（保持原长，更可能正确），最后才考虑去数字
    subs = set()
    def rec(path, idx):
        if idx == len(digits):
            s = list(tok)
            for (pos, ch), rep in zip(digits, path):
                s[pos] = rep
            subs.add(''.join(s)); return
        pos, ch = digits[idx]
        for rep in DIGIT_MAP.get(ch, [ch]):
            rec(path + [rep], idx + 1)
    rec([], 0)
    for cand in sorted(subs, key=len):
        if is_valid(cand):
            if tok[0].isupper() or cand in PROPER:
                cand = cand[:1].upper() + cand[1:]
            return cand
    removal = re.sub(r'[0-9]', '', tok)
    if is_valid(removal):
        if tok[0].isupper() or removal in PROPER:
            removal = removal[:1].upper() + removal[1:]
        return removal
    return tok

ALPHA_SEG = re.compile(r"([A-Za-z0-9][A-Za-z0-9'\-]*(?:\s+[A-Za-z0-9][A-Za-z0-9'\-]*)*)")
TOKEN_SPLIT = re.compile(r"[^A-Za-z0-9']+")

def segment_tokens(tokens):
    out = []
    i = 0
    n = len(tokens)
    while i < n:
        best = None
        for j in range(i + 1, n + 1):
            cand = ''.join(tokens[i:j])
            if should_merge(cand, tokens[i:j]):
                best = (j, cand)  # 取最长（最后出现）的合法合并
        if best:
            out.append(best[1]); i = best[0]; continue
        t = tokens[i]
        if re.search(r'[0-9]', t):
            t = fix_digit_token(t)
        out.append(t); i += 1
    return out

def segment_merged(w):
    """粘连单词(无空格)的安全网：经评估 pyspellchecker 对极短片段判定不可靠，
       为避免引入 Th at's / on Sun day 之类二次错误，此处不做切分，原样返回。"""
    return w

# 音标遮罩（仅处理带闭合斜杠的音标；无闭合斜杠的极少见，交给解析阶段容错）
PHON1 = re.compile(r'/[^/\n]*?/')

def correct_line(line):
    store = {}
    cnt = [0]
    def mask(m):
        # 占位符只含非字母数字字节(\x00)，确保 ALPHA_SEG/TOKEN_SPLIT/fix_digit 不会误改它
        key = '\x00PHON%d\x00' % cnt[0]
        store[key] = m.group(0); cnt[0] += 1
        return key
    line = PHON1.sub(mask, line)

    def repl(m):
        seg = m.group(1)
        tokens = [t for t in TOKEN_SPLIT.split(seg) if t]
        if not tokens:
            return m.group(0)
        merged = segment_tokens(tokens)
        fixed = [MANUAL_FIX.get(t, segment_merged(t)) for t in merged]
        return ' '.join(fixed)
    line = ALPHA_SEG.sub(repl, line)
    for k, v in store.items():
        line = line.replace(k, v)
    return line

if __name__ == '__main__':
    SRC = r"K:\2026年上海初中考纲词汇用法手册.txt"
    lines = open(SRC, encoding='utf-8').read().split('\n')
    out = [correct_line(ln) for ln in lines]
    changed = sum(1 for a, b in zip(lines, out) if a != b)
    print("总行数:", len(lines), " 改变行数:", changed)
    samples = [(a, b) for a, b in zip(lines, out) if a != b]
    print("\n=== 抽样校正（前 60 条）===")
    for a, b in samples[:60]:
        print("  -", a.strip()[:76])
        print("  +", b.strip()[:76])
    ENTRY_RE = re.compile(r'^\s*(?:[√◆→>])?\s*(\d+)\s*[\.、]\s*([*★]*)\s*([A-Za-z0-9][A-Za-z0-9\.\'\-]*)\s*(\([^)]*\))?\s*(.*)$')
    before = set(); after = set()
    for ln in lines:
        m = ENTRY_RE.match(ln)
        if m and m.group(3): before.add(m.group(3).strip())
    for ln in out:
        m = ENTRY_RE.match(ln)
        if m and m.group(3): after.add(m.group(3).strip())
    print("\nheadword 前/后:", len(before), len(after))
    print("新增:", sorted(after - before)[:60])
    print("消失:", sorted(before - after)[:60])
