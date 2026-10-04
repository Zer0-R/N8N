// Quiz Muz Rappel : construit UNIQUEMENT à partir du texte en base (aucune information inventée).
// Même date → même quiz (graine = date Europe/Paris) : la question (13h) et la réponse (20h) se retrouvent
// sans rien mémoriser entre les deux exécutions.
function construireQuiz(rows, dateStr) {
  let h = 2166136261;
  for (const ch of 'muz-quiz-' + dateStr) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619); }
  let s = h >>> 0;
  const rnd = () => { s = (s + 0x6D2B79F5) >>> 0; let t = s; t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  const melanger = a => { const b = [...a]; for (let i = b.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [b[i], b[j]] = [b[j], b[i]]; } return b; };
  const plat = t => String(t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[’'`]/g, "'").toLowerCase();

  // Compagnons : nom canonique → variantes écrites dans la base.
  const COMPAGNONS = {
    'Abou Houreira': ['Abou Houreira'], "'Abdallah Ibn 'Abbas": ["'Abdallah Ibn 'Abbas", "Ibn 'Abbas"],
    'Anas Ibn Malik': ['Anas Ibn Malik', 'Anas'], "'Abdallah Ibn Mas'oud": ["'Abdallah Ibn Mas'oud", "Ibn Mas'oud"],
    "'Aïcha": ["'Aicha", 'Aicha', "'Aïcha", 'Aïcha'], "Abou Sa'id Al Khoudri": ["Abou Sa'id Al Khoudri"],
    "'Abdallah Ibn 'Omar": ["'Abdallah Ibn 'Omar", "Ibn 'Omar"], "Jabir Ibn 'Abdillah": ["Jabir Ibn 'Abdillah", 'Jabir Ibn Abdillah', 'Jabir'],
    "'Othman Ibn 'Affan": ["'Othman Ibn 'Affan"], "'Omar Ibn Al Khattab": ["'Omar Ibn Al Khattab"],
    "'Oqba Ibn 'Amir": ["'Oqba Ibn 'Amir"], 'Abou Dhar': ['Abou Dhar'], "'Abdallah Ibn 'Amr": ["'Abdallah Ibn 'Amr"],
    "Abou Moussa Al Ach'ari": ["Abou Moussa Al Ach'ari", 'Abou Moussa'], 'Abou Darda': ['Abou Darda'],
    "Sahl Ibn Sa'd": ["Sahl Ibn Sa'd"], 'Abou Oumama Al Bahili': ['Abou Oumama Al Bahili', 'Abou Oumama'],
  };
  // Recueils : nom canonique → variantes. Les « grands » servent de mauvaises réponses.
  const RECUEILS = {
    'Boukhari': ['Boukhari'], 'Mouslim': ['Mouslim'], 'Tirmidhi': ['Tirmidhi'], 'Abou Daoud': ['Abou Daoud'],
    'Ahmed': ['Ahmed', "l'imam Ahmed"], 'Nasai': ['Nasai', "Nasa'i"], 'Ibn Maja': ['Ibn Maja'],
    'Tabarani': ['Tabarani'], 'Ibn Abi Chayba': ['Ibn Abi Chayba'], 'Al Hakim': ['Al Hakim', 'Hakim'],
    'Ibn Hibban': ['Ibn Hibban'], 'Al Bayhaqi': ['Al Bayhaqi', 'Bayhaqi'], 'Al Bazar': ['Al Bazar'],
    'Ibn Khouzeima': ['Ibn Khouzeima'], 'Darimi': ['Darimi'],
  };
  const GRANDS = ['Boukhari', 'Mouslim', 'Tirmidhi', 'Abou Daoud', 'Ahmed', 'Nasai', 'Ibn Maja'];
  const contient = (texte, variantes) => variantes.some(v => new RegExp(`(^|[^a-z])${plat(v).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}([^a-z]|$)`).test(plat(texte)));

  const analyser = r => {
    const t = String(r.description_full || '').replace(/\r/g, '');
    const propre = x => x.replace(/\s*\((?:\d+|\*+)\)/g, '').replace(/\s+/g, ' ').trim();
    // Texte du hadith = passage entre « D'après … : » et « (Rapporté par … ) » (jamais l'explication qui suit).
    const debut = t.search(/D.apr[èe]s /), fin = t.search(/\(Rapport[ée] par/);
    if (debut < 0 || fin <= debut) return null;
    const passage = t.slice(debut, fin);
    const q = passage.match(/«([\s\S]+?)»/);
    const narration = passage.replace(/^D.apr[èe]s [^:]*:\s*/, '');
    const citation = propre(q ? q[1] : (narration !== passage ? narration : ''));
    if (citation.length < 25) return null;
    const ref = (t.match(/\((Rapport[ée] par[\s\S]+?)\)\s*$/m) || [])[1];
    const out = { r, citation, reference: ref ? propre(ref) : '' };
    // Rapporteur : nom juste avant « (qu'Allah l'agrée / les agrée) ».
    const m = t.match(/D.apr[èe]s ([^:«\n]{3,160}?)\s*\(qu.Allah (?:l.agr[ée]e|les agr[ée]e)/);
    if (m) {
      const nom = m[1].split(',').pop().trim();
      const canon = Object.keys(COMPAGNONS).find(k => COMPAGNONS[k].some(v => plat(v) === plat(nom)));
      if (canon && !contient(citation, COMPAGNONS[canon])) {
        out.rapporteur = canon;
        out.phrase_rapporteur = `D'après ${nom} (qu'Allah l'agrée)`;
      }
    }
    // Recueil : un seul recueil connu cité dans tout le texte, sinon ambigu → pas de question.
    if (ref) {
      const cites = Object.keys(RECUEILS).filter(k => contient(t, RECUEILS[k]));
      if (cites.length === 1) out.recueil = cites[0];
    }
    return out;
  };

  const jour = Math.floor(Date.parse(dateStr + 'T12:00:00Z') / 86400000);
  const ordre = jour % 2 === 0 ? ['rapporteur', 'recueil'] : ['recueil', 'rapporteur'];
  const candidats = melanger(rows);
  for (const type of ordre) {
    for (const r of candidats) {
      const a = analyser(r);
      if (!a || !a[type]) continue;
      const texteComplet = String(r.description_full || '');
      let bonne, fausses, question;
      if (type === 'rapporteur') {
        bonne = a.rapporteur;
        fausses = melanger(Object.keys(COMPAGNONS).filter(k => k !== bonne && !contient(texteComplet, COMPAGNONS[k]))).slice(0, 2);
        question = 'Quel Compagnon a rapporté ce hadith ?';
      } else {
        bonne = a.recueil;
        fausses = melanger(GRANDS.filter(k => k !== bonne && !contient(texteComplet, RECUEILS[k]))).slice(0, 2);
        question = 'Dans quel recueil ce hadith est-il rapporté ?';
      }
      if (fausses.length < 2) continue;
      const options = melanger([bonne, ...fausses]);
      const lettre = 'ABC'[options.indexOf(bonne)];
      let extrait = a.citation;
      if (extrait.length > 260) extrait = extrait.slice(0, 250).replace(/\s+\S*$/, '') + ' …';
      return {
        date: dateStr, hadith_id: Number(r.id), titre: r.title, categorie: r.category, type, question,
        extrait, options, bonne_lettre: lettre, bonne_reponse: bonne,
        rapporteur_phrase: a.phrase_rapporteur || '', reference: a.reference,
      };
    }
  }
  return null;
}
if (typeof module !== 'undefined') module.exports = { construireQuiz };
