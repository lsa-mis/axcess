"""Round 3 diagnostic: do Tab and Shift+Tab reach the same stops? (KAFE traps)

For each KAFE subject (replayed offline), walk focus from <body> with Tab and
with Shift+Tab for 3x the static tabbable count (cap 500) and compare the sets
of stops reached, a radio group counting as one stop. Output: one JSON line
per subject. Scored against KAFE's Type 2 (keyboard trap) labels in
RESULTS.md; the signal was rejected. Run from the repo root:

    uv run python experiments/tabbing/ab/tab_asymmetry.py [-v] SUBJECT...
"""
import asyncio, sys, json
sys.path[:0]=[".", "src", "experiments/tabbing/literature-replication"]
from playwright.async_api import async_playwright
from tools import flowfile, kafe_matrix, replay
SIG = """() => { let ae=document.activeElement; while(ae&&ae.shadowRoot&&ae.shadowRoot.activeElement) ae=ae.shadowRoot.activeElement;
 if(!window.__d) window.__d={m:new WeakMap(),n:1}; if(!ae||ae===document.body) return [0,'body'];
 if(ae.type==='radio'&&ae.name){ const k='radio:'+ae.name; return [k,k]; }
 if(!__d.m.has(ae)) __d.m.set(ae,__d.n++); return [__d.m.get(ae), (ae.tagName+' '+(ae.getAttribute('class')||'')).slice(0,40)+' '+(ae.textContent||ae.value||'').trim().slice(0,20)]; }"""
TAB = """() => document.querySelectorAll('a[href],button,input,select,textarea,[tabindex]:not([tabindex="-1"])').length"""
async def walk(pg, key, n):
    await pg.evaluate("() => { document.activeElement && document.activeElement.blur && document.activeElement.blur(); document.body.focus(); }")
    out=[]
    for _ in range(n):
        await pg.keyboard.press(key); out.append(await pg.evaluate(SIG))
    return out
async def one(b, subj, verbose):
    index = flowfile.load_exchanges(kafe_matrix.capture_path(subj).read_bytes())
    url = kafe_matrix.entry_url(index); router = replay.ReplayRouter(index)
    ctx = await b.new_context(viewport=kafe_matrix.VIEWPORT, service_workers="block")
    try:
        await router.attach(ctx); pg = await ctx.new_page()
        await pg.goto(url, wait_until="load", timeout=60000); await pg.wait_for_timeout(3000)
        n = min(await pg.evaluate(TAB) * 3 + 20, 500)
        fwd = await walk(pg, "Tab", n); rev = await walk(pg, "Shift+Tab", n)
        F={x[0] for x in fwd if x[0]!=0}; R={x[0] for x in rev if x[0]!=0}
        names={**dict((a,bn) for a,bn in fwd), **dict((a,bn) for a,bn in rev)}
        out={"s":subj,"presses":n,"F":len(F),"R":len(R),"RminusF":len(R-F),"FminusR":len(F-R)}
        if verbose: out["onlyR"]=[names[i] for i in list(R-F)[:6]]; out["onlyF"]=[names[i] for i in list(F-R)[:6]]
        return out
    except Exception as e:
        return {"s":subj,"err":str(e)[:80]}
    finally:
        await ctx.close()
async def main(subjects, verbose):
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        for s in subjects: print(json.dumps(await one(b, s, verbose)), flush=True)
        await b.close()
v = sys.argv[1]=="-v"; subs = sys.argv[2:] if v else sys.argv[1:]
asyncio.run(main(subs, v))
