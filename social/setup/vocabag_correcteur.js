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
      const tous = type === 'mot' ? m : normaliser(texte).split(' ').filter(Boolean).flatMap(x => CJK.test(x) ? [...x].filter(c => CJK.test(c)) : [x]);
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
  const significatifs = mots(texte);
  const brut = normaliser(texte).split(' ').filter(Boolean);
  if (!brut.length) return null;
  const meilleurDe = (liste, motsCommentaire) => {
    let m = null;
    for (const c of liste) {
      const trouves = c.mots.filter(x => motsCommentaire.some(y => proche(y, x))).length;
      const score = trouves / c.mots.length;
      if (!m || score > m.score || (score === m.score && c.mots.length > m.cible.mots.length)) m = { score, trouves, cible: c };
    }
    return m;
  };
  // 1) la phrase prime : ≥ 85 % des mots significatifs → bravo ; ≥ 50 % et au moins 2 mots → presque
  const p = meilleurDe(cands.filter(c => c.type === 'phrase' && c.mots.length >= 2), significatifs);
  // « Bravo » : il faut aussi les petits mots (« is », « de »…), sinon c'est « Presque »
  const complet = c => c.tous.filter(x => brut.some(y => proche(y, x) || y.includes(x))).length / c.tous.length;
  if (p && p.score >= 0.85 && complet(p.cible) >= 0.85) return { ...p, type: 'bravo' };
  if (p && ((p.score >= 0.5 && p.trouves >= 2) || p.score >= 0.85)) return { ...p, type: 'presque' };
  // 2) sinon un mot du Reel écrit seul (commentaire court, mot exact)
  if (brut.length <= 3) {
    const w = meilleurDe(cands.filter(c => c.type === 'mot'), brut.flatMap(x => CJK.test(x) ? [x, ...[...x]] : [x]));
    if (w && w.score === 1) return { ...w, type: 'bravo' };
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

if (typeof module !== 'undefined') module.exports = { normaliser, mots, candidats, evaluer, reponse };
