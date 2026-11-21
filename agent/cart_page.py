import re
"""The order page the agent texts: review items, change quantity or swap, then pay once with Stripe."""
import os
from html import escape

from .pricing import quote


def cart_url(gid: str) -> str:
    base = os.environ.get("PUBLIC_URL") or "https://personal-agents-production-81468651.up.railway.app"  # as agent/connect.py
    return f"{base.rstrip('/')}/cart/{gid}"


_STATUS = {"awaiting_payment": "Waiting for your payment", "fulfilling": "Paid. Placing your orders now",
           "done": "Done. Your orders are placed", "stopped": "Stopped. Nothing more will be bought"}

_CSS = """
:root{--bg:#f6f5f1;--card:#fff;--ink:#1c2321;--muted:#5d6763;--line:#dfe3e0;--accent:#1f5c46;--accent-ink:#fff;
--warn-bg:#fff4d6;--warn-ink:#6b4a00;--ok-bg:#e3f1ea;--ok-ink:#1f5c46}
@media (prefers-color-scheme:dark){:root{--bg:#0f1513;--card:#18201d;--ink:#e8ece9;--muted:#9aa6a1;--line:#2b3531;
--accent:#5fbf94;--accent-ink:#0b1310;--warn-bg:#3a2f12;--warn-ink:#f2d58a;--ok-bg:#16332a;--ok-ink:#8fd9b6}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
main{max-width:640px;margin:0 auto;padding:20px 16px 48px}
h1{font-size:1.6rem;letter-spacing:-.01em;margin:0 0 2px}.note{margin:10px 0 0;font-size:.9rem;color:var(--warn-ink)}.reason{color:var(--muted);font-size:.9rem}.card{box-shadow:0 1px 2px rgba(0,0,0,.04)}
.status{display:inline-block;margin:6px 0 18px;padding:4px 12px;border-radius:999px;background:var(--ok-bg);color:var(--ok-ink);font-weight:600;font-size:.9rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin:0 0 12px}
.name{font-weight:600;margin:0 0 2px}
.meta,.small{color:var(--muted);font-size:.9rem}
.reason{margin:8px 0;font-size:.95rem}
.badge{display:inline-block;background:var(--warn-bg);color:var(--warn-ink);border-radius:6px;padding:2px 8px;font-weight:700;font-size:.85rem}
.alerts{margin:4px 0 0;padding-left:20px;color:var(--warn-ink);font-size:.9rem}
a{color:var(--accent)}
.row{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:10px;flex-wrap:wrap}
.step{display:flex;align-items:center;gap:6px}
.step button{width:44px;height:44px;border-radius:10px;border:1px solid var(--line);background:var(--bg);color:var(--ink);font-size:1.3rem}
.step span{min-width:2ch;text-align:center;font-weight:600}
select{-webkit-appearance:none;appearance:none;width:100%;min-height:44px;margin-top:10px;border-radius:10px;border:1px solid var(--line);background:var(--bg);color:var(--ink);font-size:.95rem;padding:0 8px}
table{width:100%;border-collapse:collapse}
td{padding:6px 0;vertical-align:top}
td:last-child{text-align:right;white-space:nowrap}
tr.total td{border-top:1px solid var(--line);font-weight:700;font-size:1.1rem;padding-top:10px}
.pay{display:block;text-align:center;background:var(--accent);color:var(--accent-ink);text-decoration:none;font-weight:700;font-size:1.1rem;padding:16px;border-radius:12px;margin:16px 0 8px}
details summary{cursor:pointer;font-weight:600;min-height:44px;display:flex;align-items:center}
details li{margin:0 0 10px;font-size:.9rem}ul.trail{list-style:none;margin:8px 0 0;padding:0 0 0 14px;border-left:2px solid var(--line,#d9dfd9)}ul.trail li{margin:0 0 14px;overflow-wrap:anywhere}ul.trail .step{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}ul.trail .step .when{margin-left:auto}.what{margin-top:2px}.chip{font-size:.72rem;padding:1px 7px;border-radius:999px;border:1px solid currentColor;opacity:.75}details.more summary{min-height:32px;font-weight:500;font-size:.82rem}details.more{font-size:.85rem}
/* polish pass: numerals, focus, states, browser surfaces */
::selection{background:var(--accent);color:var(--accent-ink)}
h1,.name{text-wrap:balance}.name{font-size:1.05rem;line-height:1.35}
main{padding-top:28px}.card{padding:18px;margin-bottom:14px}
td,.row b,.step span,.pay{font-variant-numeric:tabular-nums}
td .small{display:block;margin-top:1px}tr.total td{font-size:1.2rem;padding-top:12px}
a{text-underline-offset:3px}a:hover{text-decoration-thickness:2px}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:6px}
.step button{cursor:pointer;transition:background .15s ease-out,transform .1s ease-out}
.step button:hover{background:var(--line)}.step button:active{transform:scale(.96)}
select{cursor:pointer;padding:0 36px 0 12px;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' fill='none' stroke='%235d6763' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M1 1.5l5 5 5-5'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 14px center}
select:hover{border-color:var(--muted)}
.pay{box-shadow:0 1px 2px rgba(0,0,0,.08),0 6px 16px -6px rgba(31,92,70,.45);transition:transform .12s ease-out,filter .15s ease-out}
.pay:hover{filter:brightness(1.07)}.pay:active{transform:translateY(1px)}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
@media (max-width:420px){main{padding:18px 12px 40px}.card{padding:14px}}
.brand{margin:0 0 14px;font-weight:800;letter-spacing:-.02em;font-size:1.05rem;color:var(--accent)}
"""

_JS = """
async function edit(gid, change){
  document.body.style.opacity=.6;
  const r = await fetch('/gatherings/'+gid+'/cart', {method:'PATCH', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({changes:[change]})});
  if(!r.ok){ document.body.style.opacity=1; alert(((await r.json().catch(()=>({}))).detail)||'Could not change the cart'); return; }
  location.reload();
}
"""


def _page(title: str, body: str) -> str:
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<meta name='color-scheme' content='light dark'><title>{escape(title)}</title>"
            f"<style>{_CSS}</style></head><body><main>{body}</main><script>{_JS}</script></body></html>")


def not_found() -> str:
    return _page("Order not found", "<h1>Order not found</h1><p class='meta'>This link is old or mistyped. "
                                    "Text me what you need and I'll send a fresh one.</p>")


def _item(gid: str, i, editable: bool) -> str:
    p, e = i.product, escape
    h = (f"<div class='card'><p class='name'>{e(p.name)}</p>"
         f"<div class='meta'>{e(p.source)} &middot; {e(p.pack_size or 'size n/a')} &middot; ${p.price:.2f} each"
         f" &middot; arrives by {e(p.arrive_by.isoformat())} (est.)</div>"
         f"<div class='small'><a href='{e(p.url)}' target='_blank' rel='noopener noreferrer'>View on {e(p.source)}</a></div>")
    if i.status != "pass":
        h += ("<p class='note'><span class='badge'>Check the label</span> "
              + e("; ".join(i.alerts) or "I could not confirm every ingredient") + "</p>")
    # the alert line above already says it; do not repeat it in the reason
    why = re.sub(r"^Needs confirmation:.*?Not confirmed safe\.\s*", "", i.reason, flags=re.S)
    h += f"<p class='reason'>{e(why)}</p><div class='row'>"
    pid = e(p.id)
    if editable:
        h += (f"<div class='step' aria-label='Quantity'>"
              f"<button aria-label='One less' {'disabled' if i.quantity <= 1 else ''} "
              f"onclick='edit(\"{gid}\",{{product_id:this.dataset.p,quantity:{i.quantity - 1}}})' data-p='{pid}'>&minus;</button>"
              f"<span>{i.quantity}</span>"
              f"<button aria-label='One more' onclick='edit(\"{gid}\",{{product_id:this.dataset.p,quantity:{i.quantity + 1}}})' "
              f"data-p='{pid}'>+</button></div>")
    else:
        h += f"<span>Qty {i.quantity}</span>"
    h += f"<b>${p.price * i.quantity:.2f}</b></div>"
    if editable and i.alternatives:
        h += (f"<select aria-label='Swap item' data-p='{pid}' "
              f"onchange='if(this.value)edit(\"{gid}\",{{product_id:this.dataset.p,swap_to:this.value}})'>"
              "<option value=''>Swap for another option...</option>"
              + "".join(f"<option value='{e(a.id)}'>{e(a.name[:60])} &middot; {e(a.source)} &middot; "
                        f"{e(a.pack_size or 'size n/a')} &middot; ${a.price:.2f}</option>" for a in i.alternatives)
              + "</select>")
    return h + "</div>"


_STEPS = {"F1": "Understood the request", "F2": "Read the profile", "F3": "Messaged guests", "F4": "Checked calendars",
          "F5": "Planned what to get", "F6": "Chose a product", "F7": "Built the cart", "F8": "Approval",
          "F9": "Verified the payment", "F10": "Checked against trusted context", "F11": "Follow-up",
          "F13": "Placed the order", "F13.card": "Payment card"}


def _step(ev) -> str:
    """One audit event as a short, readable row; the full text stays one tap away."""
    full = re.sub(r"https?://\S+", "(link)", ev.decision)
    short = full if len(full) <= 170 else full[:167].rsplit(" ", 1)[0] + "..."
    chip = "<span class='chip'>simulated</span>" if ev.simulated else ""
    more = f"<details class='more'><summary>Full detail</summary>{escape(full)}</details>" if short != full else ""
    return (f"<li><div class='step'><b>{escape(_STEPS.get(ev.node_id, ev.node_id))}</b>{chip}"
            f"<span class='small when'>{escape(ev.time.strftime('%H:%M UTC'))}</span></div>"
            f"<div class='what'>{escape(short)}</div>{more}</li>")


def render(g, audit) -> str:
    e, gid = escape, g.id  # gid is 12 hex chars (Workflow._path checks), safe inside the JS
    items = g.cart.items if g.cart else []
    q = quote(g.cart) if g.cart else None
    editable = g.status == "awaiting_payment"
    body = (f"<p class='brand'>Blackout</p><h1>Your order</h1><p class='meta'>You asked: \u201c{e(g.request)}\u201d</p><div class='status'>{e(_STATUS.get(g.status, 'Getting your cart ready'))}</div>"
            + "".join(_item(gid, i, editable) for i in items))
    if q:
        body += (f"<div class='card'><table>"
                 f"<tr><td>Subtotal</td><td>${q['subtotal']:.2f}</td></tr>"
                 f"<tr><td>Shipping (estimated)<div class='small'>{e(q['shipping_note'])}</div></td><td>${q['shipping']:.2f}</td></tr>"
                 f"<tr><td>Estimated tax<div class='small'>{e(q['tax_note'])}</div></td><td>${q['tax']:.2f}</td></tr>"
                 f"<tr class='total'><td>Total</td><td>${q['total']:.2f}</td></tr></table></div>")
    if editable and g.checkout_url and items:
        body += (f"<a class='pay' href='{e(g.checkout_url)}'>Pay ${q['total']:.2f} with Stripe</a>"
                 "<p class='small'>You only authorize the payment. After that I place the orders and text you the "
                 "receipt. Card details stay with Stripe.</p>"
                 "<p class='small'>Demo: retailer order placement is simulated and Stripe is in test mode.</p>")
    if g.status in ("fulfilling", "done"):
        orders = [f"{ev.inputs['source']}: order {ev.inputs.get('order_id')} (simulated)" for ev in audit
                  if ev.node_id == "F13" and "source" in ev.inputs]
        arrive = max((i.product.arrive_by for i in items), default=None)
        body += ("<div class='card'><p class='name'>Receipt</p><ul>"
                 + "".join(f"<li>{e(o)}</li>" for o in orders or ["Placing orders now..."])
                 + f"</ul><p class='meta'>Ships to {e(g.ship_to)}"
                 + (f". Estimated arrival {arrive.isoformat()}" if arrive else "") + ".</p>"
                 "<p class='small'>Retailer orders and the virtual card are simulated in this demo; "
                 "the Stripe payment was a test-mode payment.</p></div>")
    body += ("<details class='card'><summary>Why these items? (audit trail)</summary><ul class='trail'>"
             + "".join(_step(ev) for ev in audit) + "</ul></details>")
    return _page(f"Your order: {g.request[:40]}", body)
