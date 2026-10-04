// Correcteur des commentaires VocaBag : la personne a-t-elle écrit la phrase (ou le mot) du Reel ?
// Utilisé par le nœud « Réponses à faire » de « VocaBag - Réponses commentaires » (build_vocabag_reponses.py).
// candidats(reveals) : textes attendus tirés de <folder>_words.json ; evaluer(texte, cands) → null | {type, cible, score}

function normaliser(s) {
  return String(s || '')
    .toLowerCase()
    .normalize('NFD').replace(/\p{M}/gu, '')            // accents latins + harakat arabes
    .replace(/[أإآٱ]/g, 'ا').replace(/ة/g, 'ه').replace(/ى/g, 'ي').replace(/ـ/g, '')
    .replace(/[ʿʾ'’`´]/g, '')
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .replace(/\s+/g, ' ').trim();
}

// Chinois / japonais : pas d'espaces → un caractère = un mot. Ailleurs : mots de 3 lettres ou plus
// (« la », « de », « mi », « في »… ne suffisent pas à reconnaître une phrase).
const CJK = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}]/u;
function mots(s) {
  const out = [];
  for (const m of normaliser(s).split(' ').filter(Boolean)) {
    if (CJK.test(m)) out.push(...[...m].filter(c => CJK.test(c)));
    else if ([...m].length >= 3) out.push(m);
  }
  return out;
}
function tousMots(s) {
  return normaliser(s).split(' ').filter(Boolean).flatMap(x => CJK.test(x) ? [...x].filter(c => CJK.test(c)) : [x]);
}

function distance(a, b) {               // Levenshtein (mots courts)
  const m = a.length, n = b.length;
  if (Math.abs(m - n) > 2) return 3;
  let prev = Array.from({ length: n + 1 }, (_, j) => j);
  for (let i = 1; i <= m; i++) {
    const cur = [i];
    for (let j = 1; j <= n; j++) cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    prev = cur;
  }
  return prev[n];
}

const proche = (a, b) => a === b || (a.length >= 4 && b.length >= 4 && distance(a, b) <= 1);

function candidats(reveals) {
  const out = [];
  for (const r of reveals || []) {
    const translit = String(r.answerDisplay || '').split('\n')[0];
    const ajout = (texte, type) => {
      const m = type === 'mot' ? normaliser(texte).split(' ').filter(Boolean) : mots(texte);
      const tous = type === 'mot' ? m : tousMots(texte);
      if (m.length) out.push({ texte, mots: m, tous, type, phrase: r.example_sentence, translit,
                                  traduction: type === 'mot' ? r.translation : r.example_translation });
    };
    ajout(r.example_sentence, 'phrase');
    if (translit && translit !== r.example_sentence) ajout(translit, 'phrase');
    ajout(r.word, 'mot');
    if (r.transliteration) ajout(r.transliteration, 'mot');
  }
  return out;
}

function evaluer(texte, cands) {
  const brut = normaliser(texte).split(' ').filter(Boolean);
  if (!brut.length) return null;
  const ct = tousMots(texte);                                    // mots entiers du commentaire (CJK : caractères)
  const present = x => ct.some(y => proche(y, x));
  // 1) la phrase prime. « Bravo » : ≥ 85 % de la phrase complète ET des mots significatifs (≥ 3 lettres) ;
  //    « Presque » : ≥ 50 % des deux, au moins 2 mots en commun dont 1 significatif.
  //    Phrase reconnue dès 3 mots (petits mots compris) ou 2 mots significatifs.
  let p = null;
  for (const c of cands.filter(c => c.type === 'phrase' && (c.tous.length >= 3 || c.mots.length >= 2))) {
    const nTous = c.tous.filter(present).length, nSig = c.mots.filter(present).length;
    const full = nTous / c.tous.length, sig = c.mots.length ? nSig / c.mots.length : full;
    const score = Math.min(full, sig);
    if (!p || score > p.score || (score === p.score && c.tous.length > p.cible.tous.length)) p = { score, full, sig, nTous, nSig, cible: c };
  }
  if (p && p.full >= 0.85 && p.sig >= 0.85) return { ...p, type: 'bravo' };
  if (p && p.full >= 0.5 && p.sig >= 0.5 && p.nTous >= 2 && (p.nSig >= 1 || !p.cible.mots.length)) return { ...p, type: 'presque' };
  // 2) sinon un mot du Reel écrit seul (commentaire de 3 mots max). Chinois / japonais : le commentaire doit être
  //    exactement le mot (sinon « 我不好意思 » validerait « 好 »).
  if (brut.length <= 3) {
    const colle = brut.join('');
    for (const c of cands.filter(c => c.type === 'mot')) {
      const ok = CJK.test(c.texte) ? colle === c.mots.join('') : c.mots.every(x => brut.some(y => proche(y, x)));
      if (ok) return { score: 1, cible: c, type: 'bravo' };
    }
  }
  return null;
}

function reponse(ev) {
  const c = ev.cible;
  if (ev.type === 'bravo')
    return c.type === 'mot'
      ? `Bravo 👏 C’est bien ça : « ${c.texte} »${c.traduction ? ' = ' + c.traduction : ''} 🎉`
      : `Bravo 👏 C’est exactement ça !${c.traduction ? ' (' + c.traduction + ')' : ''} 🎉`;
  return `Presque 💪 La phrase exacte : « ${c.phrase} »` + (c.translit && c.translit !== c.phrase ? ` (${c.translit})` : '');
}

if (typeof module !== 'undefined') module.exports = { normaliser, mots, tousMots, candidats, evaluer, reponse };
