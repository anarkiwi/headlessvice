from vsiddump import reg_processor


def test_process_data():
    processor = reg_processor()
    assert b"1 0 2 3\n6 0 5 6\n" == processor.process("1 2 3\n1 2 3\n4 5 6\n")
