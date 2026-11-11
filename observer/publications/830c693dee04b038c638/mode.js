/* Public content only: no discovery, research or demonstration loader. */
(() => {
  const fail = () => { document.querySelector('#main').textContent = '内容暂时未能加载，请稍后重试。'; };
  const data = document.createElement('script');
  data.src = 'real-data.js?v=198991a9c9e40d05';
  data.onerror = fail;
  data.onload = () => {
    const app = document.createElement('script');
    app.src = 'app.js?v=198991a9c9e40d05';
    app.onerror = fail;
    document.head.append(app);
  };
  document.head.append(data);
})();
