const knowledgeNav = document.querySelector('#knowledgeNav');
const knowledgeMain = document.querySelector('#knowledgeMain');

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

const KNOWLEDGE_SECTIONS = [
  {
    id: 'exegesis',
    kicker: '训诂知识',
    title: '训释',
    items: [
      { number: '1', term: '训释', description: '用语言来表述文献语言意义的工作。根据训释目的不同，可分为声训、形训和义训，根据训释的语言结构方式不同，可分为直训和义界。' },
      { number: '2', term: '声训', description: '用音同音近的词来解释被训释词语的训释。古代声训有语言声训、文字声训、民俗声训、义理声训等。语言声训指同源词互训，例如“天，颠也”“涧，间也”。' },
      { number: '3', term: '形训', description: '通过对汉字形体的分析来探求本义的训释。例如“塵，鹿行杨土也”。' },
      { number: '4', term: '义训', description: '直接从意义上解释词语的训释。例如“口，人所以言食也”。' },
      { number: '5', term: '直训', description: '以单词训释单词的训释方式。由一个或数个直训可以构成单训、互训、递训、同训。' },
      { number: '6', term: '单训', description: '训释词与被训释词只是单向训释的直训。例如“璐，玉也”。' },
      { number: '7', term: '互训', description: '两个词互相训释的直训。例如“排，挤也”“挤，排也”。' },
      { number: '8', term: '递训', description: '也称“迭训”。两个以上的词递相训释的直训。例如“语，论也”“论，议也”“议，语也”。' },
      { number: '9', term: '同训', description: '同一个词训释几个词的直训。例如“八，分也”“异，分也”“判，分也”“件，分也”。' },
      { number: '10', term: '义界', description: '用定义来表述词义内容的训释方式。典型的义界结构是“义值差+主训词”。例如“观，谛视也”，其中“谛”为义值差，“视”为主训词。' },
      { number: '11', term: '主训词', description: '在义界中用来表示与被训释词相同意义成分的词语。一般是被训释词的同义词或同类词。例如“”' },
      { number: '12', term: '义值差', description: '在义界中表示被训释词语义特征的用语。例如“京，人所为绝高丘也”，“人所为”和“绝高”为义值差。' },
      { number: '13', term: '随文释义', description: '也称“随文立训”或“隶属之训诂”。附在典籍原文中，来解释字、词、句以及篇章等意义的训释。例如“关关雎鸠”，《毛诗故训传》：“关关，和声也。”' },
      { number: '14', term: '专书训释', description: '脱离了典籍原文，按一定原则编排在专属中的训释。例如《说文解字》《方言》等书中的训释。' },
      { number: '15', term: '词义训释', description: '表述被训释词概括的语言意义的训释。例如“观，谛听也”“淑，善也”。' },
      { number: '16', term: '文意训释', description: '表述被训释词在言语环境中的具体含义的训释。例如“母也天只，不谅人只”，《毛诗故训传》：“天谓父也。”“天”本无“父亲”之义，在此环境中特指“父亲”。' },
      { number: '17', term: '反训', description: '也称“反相训”“相反为训”“正反同辞”等。传统训诂学术语。原指训释词与被训释词意义相反或用两个反义词训释同一个词的现象。实际上前人所谓“反训”并非训释方式，它反映了因引申形成的词义的对立相通的现象，其存在是有条件的。例如“副”有“分”“合”二义，它的本义是把一物剖成两半，然后再合起来。所以，“分”和“合”看似对立，却是相通的。' },
      { number: '18', term: '训释用语', description: '传统训诂学用于专门表示训释语和被训释语之间某种关系的程序化用语。释词用的有“曰”“为”“谓之”“犹”“之为言”等；注音用的有“读如”“读若”等；明字用的有“当作”“当为”等；阐释章句用的有“言”“章旨”等。例如“小曰羔，大曰羊”，用“曰”做成的训释说明“羊”和“羔”具有不同特征。' },
    ],
  },
  {
    id: 'relations',
    kicker: '训诂知识',
    title: '训诂所见音义及字、词、句关系',
    items: [
      { number: '19', term: '本义', description: '根据汉字形体分析出的意义，现代训诂学把前人所说的本义离析为造意与实义两个概念。' },
      { number: '20', term: '造意', description: '汉字依据某一词义采用的构造方案中显示的具体构造意图。也有人称为“字的本义”。例如“塵”从“鹿”从“土”的构造方案，其意图是用“鹿行扬土”来表示其“细小尘土”的词义。' },
      { number: '21', term: '实义', description: '由汉字形体结构中反映出来的、并在文献中实际使用过的词的某一义项。也有人称为“词的本义”。例如“塵”“从鹿从土”的形体中，反映出它在文献中使用的“细小尘土”的词义。' },
      { number: '22', term: '本字', description: '专为记录某词而造、形体与词义切合的字，称作这个词的本字。例如《诗经》“济有深涉”的“涉”字义为“徒步渡水”，与“涉”的字形相合，所用即本字。' },
      { number: '23', term: '笔意', description: '能够体现原始造字意图的字形。例如“因”的本义是“席子”，造字初期象有纹路的席子之形。' },
      { number: '24', term: '笔势', description: '经过演变脱离原始造字意图的字形。例如楷书“因”从“囗”从“大”，无法反映“席子”这一本义。' },
      { number: '25', term: '引申', description: '由于人的联想，从已有的意义中不断产生相关新义的词义运动形式。例如“节”从“竹节”义联想为状态相似的“关节”义。' },
      { number: '26', term: '引申义', description: '通过引申方式而产生的意义。' },
      { number: '27', term: '引申义列', description: '以本义为出发点，对多义词的诸引申义项按逻辑关系加以平面系联整理而成的一个连贯的意义系列。' },
      { number: '28', term: '假借', description: '1在造字初期借用同音字来记录未造字的词，或以音同的字来替代没有实义的虚词的做法，即本无其字的假借。2也称“同音借用”或“通假”，在本字已经存在的情况下，借用音同或音近而意义无关的字来替代本字，即本有其字的假借。例如先秦已有记录面貌的“頌”字，而典籍常写作“容”。' },
      { number: '29', term: '假借义', description: '因字的假借而产生的与本字无关的词义。' },
      { number: '30', term: '同源通用', description: '因词的派生而孳乳出的新字，在尚未完全习用的过渡阶段与源字通用或者新字之间混用的现象。例如“正”孳乳出“政”，又与“政”通用。' },
      { number: '31', term: '孳乳', description: '在词的派生推动下，由记录源词的字分化出新字的现象。例如“正”孳乳出“政”。' },
      { number: '32', term: '变易', description: '意义不变而字形变化的同词异字现象。例如“厷”写为“肱”。' },
      { number: '33', term: '词源', description: '构词的理据，即词的音义结合的来源。' },
      { number: '34', term: '字源', description: '1传统训诂学中同“词源”。2也称“形源”。用来指汉字字形的最早来源。' },
      { number: '35', term: '原生词', description: '语言产生之初，音义按约定俗成原则结合的词。' },
      { number: '36', term: '派生词', description: '在旧词的基础上分化出的新词称作旧词的派生词。' },
      { number: '37', term: '同源词', description: '由同一根词直接或间接派生出来的词互为同源词。' },
      { number: '38', term: '根词', description: '也称“语根”。同族派生词的总根。在词族中，根词只有一个。' },
      { number: '39', term: '源词', description: '直接派生他词的词称作这个派生词的源词。例如“赴”是“讣”的源词。' },
      { number: '40', term: '词族', description: '由同一语根派生的全部同源词的聚合。' },
      { number: '41', term: '对文则异，散文则通', description: '也称“统言，析言”“浑言，析言”。同义词之间泛称时可以通用，相对出现时又必须区别的现象。例如“鸟”在一般情况下是长尾鸟和短尾鸟的通称，而在与“隹”相对时，只表示长尾鸟。' },
      { number: '42', term: '重言词', description: '也称“重言形况字”。相当于后来的叠音词。由相同汉字重叠用以形容态貌或比拟声音的双音节单纯词。例如“苍苍”“喈喈”。' },
      { number: '43', term: '联绵词', description: '也称“联绵词”“謰语”。由两个音节连缀成义而且上下字具有一定声音关系的单纯词。根据上下两字的声音关系不同，可分为双声联绵词（例如“淋漓”“仿佛”）、叠韵连绵词（例如“徘徊”“逍遥”）、双声叠韵联绵词（例如“缤纷”“辗转”）、非双声叠韵联绵词（例如“扶摇”）。' },
      { number: '44', term: '破读', description: '也称“读破”“破字”。用本字改读通假字的现象和方法。例如《诗经》“四之日其蚤”，“蚤”应破读为“早”；《论语》“天下有道则见”，“见”应改读为“现”。' },
      { number: '45', term: '句读', description: '古代的一种标点方法。一句结束为句，句中停顿为读，合称句读。' },
    ],
  },
  {
    id: 'methods',
    kicker: '训诂知识',
    title: '训诂方法与禁忌',
    items: [
      { number: '46', term: '形音义互求', description: '训诂方法的一种。根据汉字形义统一、与音有密切联系的原理，利用三者的关系互相求证。' },
      { number: '47', term: '以形索义', description: '训诂方法的一种。根据汉字形义统一的特点来推求本义，并以本义统率引申义、辨别假借义。' },
      { number: '48', term: '因声求义', description: '训诂方法的一种。运用文献语言的材料，依循语音的相互关系和音变的线索，寻找同源字之间音变的轨迹和确定借用字之间音异的状况，达到探求文献词义的目的。' },
      { number: '49', term: '系源', description: '在根词不确定的情况下，经过系联将同源词类聚在一起的工作。' },
      { number: '50', term: '推源', description: '也称“推因”。确定派生词的根词或源词的工作。' },
      { number: '51', term: '以义证音', description: '训诂方法的一种。根据意义关系就正字读、探求古音。' },
      { number: '52', term: '比较互证', description: '训诂的方法的一种。运用词义本身的内在规律，通过词与词之间意义的关系和多义词诸义项的关系对比，达到探求和判定词义的目的。' },
      { number: '53', term: '据文证义', description: '训诂方法的一种。利用文献语境来探求或证明词义。' },
      { number: '54', term: '义素', description: '分析义位内部结构的意义单位。训诂学阐释义界的语言结构时借用西方结构语义学的术语。现代训诂学将其分为核义素、类义素和表义素。' },
      { number: '55', term: '核义素', description: '也称“源义素”。从同组同源词中提取出的经验性的意象特征。例如“稍、秒、梢、艄”可以提取出核义素“尖小一末梢”。' },
      { number: '56', term: '类义素', description: '从同类词中提取的类别特征。例如“江、河、淮、汉”可提取出类义素“河流”。' },
      { number: '57', term: '表义素', description: '从同义词中提取出的类义素以外的区别性特征。例如“徐行曰步，疾行曰趋”，“步”和“趋”都以“行”为类义素，它们之间具有区别作用的表义素为“徐”和“疾”。' },
      { number: '58', term: '义素二分法', description: '现代训诂学在利用义界对词义内部结构分析时，把词的义位切分为“类义素+核义素”或“类义素+表义素”两部分的方法。' },
      { number: '59', term: '望文生训', description: '也称“望形生训”“望文生义”。根据已经脱离原始造意的后代演变的字形或以假借字的字形来解释意义的错误做法。' },
      { number: '60', term: '增字解经', description: '也称“增字为训”。在注释中主观地添加与原义无关的字词来生成训条，造成曲解原文意义的错误做法。' },
    ],
  },
];

function renderAnchorNav(sections) {
  if (!knowledgeNav) return;

  knowledgeNav.innerHTML = sections
    .map(
      (section) => `
        <a class="knowledge-anchor-chip" href="#${escapeHtml(section.id)}">
          <span>${escapeHtml(section.title)}</span>
          <strong>${escapeHtml(String(section.items.length))} 条</strong>
        </a>
      `,
    )
    .join('');
}

function renderSection(section) {
  const cards = section.items
    .map(
      (item) => `
        <article class="card glossary-card">
          <div class="glossary-card-head">
            <span class="glossary-index">${escapeHtml(item.number)}</span>
            <h3>${escapeHtml(item.term)}</h3>
          </div>
          <p class="glossary-definition">${escapeHtml(item.description)}</p>
        </article>
      `,
    )
    .join('');

  return `
    <section id="${escapeHtml(section.id)}" class="knowledge-section">
      <div class="head-line">
        <div>
          <p class="section-kicker">${escapeHtml(section.kicker)}</p>
          <h2>${escapeHtml(section.title)}</h2>
        </div>
        <p class="knowledge-section-meta">${escapeHtml(String(section.items.length))} 条术语</p>
      </div>
      <div class="knowledge-grid">
        ${cards}
      </div>
    </section>
  `;
}

function renderKnowledge(sections) {
  if (!knowledgeMain) return;
  knowledgeMain.innerHTML = sections.map(renderSection).join('');
}

renderAnchorNav(KNOWLEDGE_SECTIONS);
renderKnowledge(KNOWLEDGE_SECTIONS);
