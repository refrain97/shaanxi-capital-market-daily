/* Public content only: no discovery, research or demonstration loader. */
(() => {
  const fail = () => { document.querySelector('#main').textContent = '内容暂时未能加载，请稍后重试。'; };
  const data = document.createElement('script');
  data.src = 'real-data.js?v=bdec2ba5bdc1b95f';
  data.onerror = fail;
  data.onload = () => {
    const app = document.createElement('script');
    app.src = 'app.js?v=bdec2ba5bdc1b95f';
    app.onerror = fail;
    document.head.append(app);
  };
  document.head.append(data);
})();
