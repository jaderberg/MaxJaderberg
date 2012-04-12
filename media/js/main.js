$(function () {

    var access_token = 'access_token=36657960.1fb234f.5bf801de2cf64301b139b2924a390a42',

        set_bgimage = function(ig_images, ig_counter, prev_ig_counter) {
            var bgimg = new Image(),
                $bgimg = $(bgimg),
                trans = 3000,
                $thisCanvas,
                $prevCanvas;
            // create the image tag
            $bgimg.addClass('bg');
            $bgimg.addClass('bgimg' + ig_counter.toString());
            $bgimg.css('top', '-100000px');
            $('body').prepend($bgimg);
            // preload the image
            bgimg.src = ig_images[ig_counter].images.standard_resolution.url;
            // once loaded blur and show
            bgimg.onload = function() {
                var options = {'amount': 2};
                $bgimg.pixastic('blurfast', options);
                $thisCanvas = $(options.resultCanvas);
                $prevCanvas = $('canvas.bgimg' + prev_ig_counter.toString());
                $thisCanvas.hide().css('top', $thisCanvas.height() + 'px').show().animate({top: '0px'}, trans);
                $prevCanvas.animate({top: '-=' + $prevCanvas.height() + 'px'}, trans, function () {$(this).remove();});
            };
        };


    $.getJSON('https://api.instagram.com/v1/users/36657960/media/recent?' + access_token + '&callback=?', function (data) {
        var ig_counter = 0,
            prev_ig_counter = -1;
        set_bgimage(data.data, ig_counter, prev_ig_counter);
        setInterval(function() {
            prev_ig_counter = ig_counter;
            ig_counter ++;
            if (ig_counter==data.data.length) {
                ig_counter = 0;
            }
            set_bgimage(data.data, ig_counter, prev_ig_counter);
        }, 15000);
    });





});
