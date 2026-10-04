const k = require('./vocabag_correcteur.js');
// Phrases réelles des Reels du 04/10 (arabe) et du 03/10 (néerlandais), copiées depuis <folder>_words.json
// (channels/ n'est pas versionné et ses fichiers sont purgés à 7 jours).
const ar = [{"word": "مكتب", "transliteration": "Maktab", "translation": "Bureau", "example_sentence": "المدير يعمل في مكتب كبير بالعمارة.", "example_translation": "Le directeur travaille dans un grand bureau.", "answerDisplay": "al-mudir yaʿmal fi maktab kabir bil-ʿimara\n(Le directeur travaille dans un grand bureau.)"}, {"word": "هاتف", "transliteration": "Hatif", "translation": "Telephone", "example_sentence": "اتصلت به عبر الهاتف أمس.", "example_translation": "Je l'ai appelé au téléphone hier.", "answerDisplay": "ittasalt-u bihi ʿabr al-hatif ams\n(Je l'ai appelé au téléphone hier.)"}, {"word": "قلم", "transliteration": "Qalam", "translation": "Stylo", "example_sentence": "نسيت قلمي في الفصل اليوم", "example_translation": "J'ai oublié mon stylo en classe aujourd'hui", "answerDisplay": "nasitu qalami fi al-fasl al-yawm\n(J'ai oublié mon stylo en classe aujourd'hui)"}];
const nl = [{"word": "de deurbel", "translation": "la sonnette", "example_sentence": "Bel aan de deurbel.", "example_translation": "Sonne à la sonnette.", "answerDisplay": "Bel aan de deurbel.\n(Sonne à la sonnette.)"}, {"word": "de ijskast", "translation": "le réfrigérateur", "example_sentence": "Het eten is in de ijskast.", "example_translation": "La nourriture est dans le réfrigérateur.", "answerDisplay": "Het eten is in de ijskast.\n(La nourriture est dans le réfrigérateur.)"}, {"word": "de woonkamer", "translation": "le salon", "example_sentence": "We zitten samen in de woonkamer.", "example_translation": "Nous sommes assis ensemble dans le salon.", "answerDisplay": "We zitten samen in de woonkamer.\n(Nous sommes assis ensemble dans le salon.)"}];
const es = [{ word: 'casa', transliteration: '', translation: 'maison', example_sentence: 'La casa de mi madre es grande.', example_translation: 'La maison de ma mère est grande.', answerDisplay: 'La casa de mi madre es grande.' }];
const zh = [{ word: '茶', transliteration: 'chá', translation: 'thé', example_sentence: '我喜欢喝茶。', example_translation: "J'aime boire du thé.", answerDisplay: 'Wǒ xǐhuān hē chá\n(J’aime boire du thé.)' }];
const hao = [{ word: '好', transliteration: 'hǎo', translation: 'bien', example_sentence: '今天天气很好。', example_translation: 'Il fait beau aujourd’hui.', answerDisplay: 'Jīntiān tiānqì hěn hǎo' }];
const fr = [{ word: 'chat', transliteration: '', translation: 'chat', example_sentence: 'Elle a deux chats.', example_translation: 'Elle a deux chats.', answerDisplay: 'Elle a deux chats.' }];
const pe = [{ word: 'perro', transliteration: '', translation: 'chien', example_sentence: 'Es mi perro.', example_translation: "C'est mon chien.", answerDisplay: 'Es mi perro.' }];
const T = [
  [hao, '我不好意思', null], [hao, '好', 'bravo'], [hao, '今天天气很好', 'bravo'],
  [fr, 'elle deux chats', 'presque'], [fr, 'Elle a deux chats', 'bravo'], [fr, 'deux', null],
  [pe, 'Es mi perro', 'bravo'], [pe, 'es mi', null], [pe, 'perro', 'bravo'],
  [es, 'Je suis de la région, trop bien', null], [es, 'La casa de mi madre es grande', 'bravo'], [es, 'la casa de mi madre', 'presque'],
  [es, 'casa', 'bravo'], [es, 'de la', null],
  [zh, '我喜欢喝茶', 'bravo'], [zh, '我喜欢', 'presque'], [zh, 'wo xihuan he cha', 'bravo'], [zh, '茶', 'bravo'], [zh, '好看', null],
  [ar, 'المدير يعمل في مكتب كبير بالعمارة', 'bravo'], [ar, 'al mudir yamal fi maktab kabir bil imara', 'bravo'],
  [ar, 'al-mudir yaʿmal fi maktab kabir', 'presque'], [ar, 'Maktab', 'bravo'], [ar, 'super vidéo merci 🙏', null], [ar, 'في', null],
  [nl, 'Bel aan de deurbel', 'bravo'], [nl, 'Het eten is in de ijskast!', 'bravo'], [nl, 'het eten in ijskast', 'presque'],
  [nl, 'Trop bien cette appli', null], [nl, 'de', null],
];
let ko = 0;
for (const [rev, t, attendu] of T) {
  const ev = k.evaluer(t, k.candidats(rev)); const got = ev ? ev.type : null;
  if (got !== attendu) ko++;
  console.log(got === attendu ? 'OK ' : 'KO ', JSON.stringify(t).padEnd(44), '→', got, ev ? ev.score.toFixed(2) + ' | ' + k.reponse(ev) : '');
}
console.log(ko ? `${ko} échec(s)` : 'tous les cas passent');
