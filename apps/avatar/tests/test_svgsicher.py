"""SVG-Whitelist: alles außer der Positivliste wird abgewiesen."""

import re

import pytest

from apps.avatar.generator import svgsicher
from apps.avatar.generator.svgsicher import SvgUnzulaessig, svg_bereinigen

NS = 'xmlns="http://www.w3.org/2000/svg"'


def svg(innen, wurzel=""):
    return f'<svg {NS} viewBox="0 0 32 48"{wurzel}>{innen}</svg>'


GUT = svg(
    '<g opacity="0.5"><rect x="1" y="2" width="3" height="4" fill="#ff0000"/>'
    '<circle cx="5" cy="5" r="2" fill="#0f0"/>'
    '<path d="M0 0h4v4h-4z" fill="#123456" transform="translate(1 2)"/>'
    '<polygon points="0,0 4,0 4,4" fill="none"/></g>'
)

BOESE = {
    "script": svg("<script>alert(1)</script>"),
    "script_mit_namespace": svg('<script type="text/javascript">x</script><rect x="1"/>'),
    "onload_am_wurzelelement": svg("", ' onload="alert(1)"'),
    "onload_am_kind": svg('<rect x="1" y="1" width="2" height="2" onload="alert(1)"/>'),
    "onclick": svg('<g onclick="x()"><rect x="1"/></g>'),
    "onmouseover_grossgeschrieben": svg('<rect x="1" OnMouseOver="x()"/>'),
    "externes_href": svg('<image href="http://evil.example/x.png" width="3" height="3"/>'),
    "href_am_rechteck": svg('<rect x="1" href="https://evil.example"/>'),
    "xlink_href": (
        f'<svg {NS} xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 32 48">'
        '<use xlink:href="http://evil.example/a.svg#b"/></svg>'
    ),
    "use_element": svg('<use href="#a"/>'),
    "foreignObject": svg('<foreignObject width="10" height="10"><div>hi</div></foreignObject>'),
    "style_attribut": svg('<rect x="1" style="fill:url(http://evil.example)"/>'),
    "style_element": svg("<style>rect{fill:red}</style>"),
    "url_in_fill": svg('<rect x="1" fill="url(#a)"/>'),
    "javascript_in_fill": svg('<rect x="1" fill="javascript:alert(1)"/>'),
    "css_expression": svg('<rect x="1" fill="expression(alert(1))"/>'),
    "text_im_element": svg("<g>hallo</g>"),
    "text_element": svg("<text>hi</text>"),
    "doctype_mit_entity": (
        '<!DOCTYPE svg [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]>'
        f'<svg {NS} viewBox="0 0 32 48"><g>&b;</g></svg>'
    ),
    "externe_entity": (
        '<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        f'<svg {NS} viewBox="0 0 32 48"><g>&x;</g></svg>'
    ),
    "cdata": svg("<g><![CDATA[x]]></g>"),
    "processing_instruction": f'<?xml-stylesheet href="http://evil.example"?><svg {NS}/>',
    "fremder_namensraum": svg('<rect xmlns:x="http://evil.example" x:foo="1" x="1"/>'),
    "fremdes_element": svg('<html xmlns="http://www.w3.org/1999/xhtml"><body/></html>'),
    "animate": svg('<rect x="1"><animate attributeName="x" to="3"/></rect>'),
    "set": svg('<rect x="1"><set attributeName="onload" to="x()"/></rect>'),
    "verschachteltes_svg": svg("<svg><rect x='1'/></svg>"),
    "falsche_viewbox": svg("", "").replace("0 0 32 48", "0 0 9999 9999"),
    "breite_am_wurzelelement": svg("", ' width="9999"'),
    "transform_mit_funktion": svg('<rect x="1" transform="matrix(1 2 3 4 5 6)"/>'),
    "pfad_mit_script": svg('<path d="M0 0 <script>"/>'),
    "zahl_mit_einheit": svg('<rect x="1px"/>'),
    "keine_wurzel": "<rect x='1'/>",
    "kein_xml": "das ist kein svg",
    "leer": "",
    "nur_leerzeichen": "   ",
    "kaputtes_xml": "<svg><g></svg>",
    "zu_gross": svg("<g/>" * 100_000),
    "zu_viele_elemente": svg("<g/>" * 500),
    "zu_tief": svg("<g>" * 10 + "</g>" * 10),
}


@pytest.mark.parametrize("name", sorted(BOESE))
def test_boeses_svg_wird_abgewiesen(name):
    with pytest.raises(SvgUnzulaessig):
        svg_bereinigen(BOESE[name])
    assert svgsicher.svg_pruefen(BOESE[name])


def test_script_meldung_nennt_das_element():
    with pytest.raises(SvgUnzulaessig, match="script"):
        svg_bereinigen(BOESE["script"])


def test_onload_meldung():
    with pytest.raises(SvgUnzulaessig, match="Ereignis"):
        svg_bereinigen(BOESE["onload_am_wurzelelement"])


def test_href_meldung():
    with pytest.raises(SvgUnzulaessig, match="href"):
        svg_bereinigen(BOESE["href_am_rechteck"])


def test_foreignobject_meldung():
    with pytest.raises(SvgUnzulaessig, match="foreignObject"):
        svg_bereinigen(BOESE["foreignObject"])


def test_gutes_svg_wird_kanonisch_zurueckgegeben():
    sauber = svg_bereinigen(GUT)
    assert sauber.startswith('<g opacity="0.5">')
    assert svgsicher.svg_pruefen(GUT) is None
    assert svg_bereinigen(GUT) == sauber  # deterministisch


def test_ausgabe_enthaelt_nur_erlaubtes():
    sauber = svg_bereinigen(GUT)
    for verboten in ("script", "href", "style", "foreignObject", "http"):
        assert verboten not in sauber
    assert not re.search(r"\son\w+=", sauber)


def test_kommentare_werden_entfernt():
    assert svg_bereinigen(svg("<!-- hallo --><rect x='1' y='1' width='2' height='2'/>")) == (
        '<rect height="2" width="2" x="1" y="1"/>'
    )


def test_whitelist_ist_klein():
    assert svgsicher.ELEMENTE == {"svg", "g", "rect", "path", "polygon", "circle"}
    assert not {a for a in svgsicher.ATTRIBUTE if a.startswith("on") or "href" in a}
